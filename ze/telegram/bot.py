import asyncio
import html as _html
from io import BytesIO
from uuid import UUID

from aiogram import Bot
from aiogram.types import CallbackQuery, ForceReply, Message

from ze.errors import ImageDownloadError
from ze.logging import bind_context, get_logger, unbind_context
from ze.progress.reporter import ProgressReporter
from ze.progress.translations import ProgressTranslations
from ze.telegram.commands import contacts_search, contacts_summary, costs_summary, memory_summary, parse_persona_command, persona_summary
from ze.telegram.formatting import md_to_html, split_html
from ze.telegram.keyboards import confirmation_keyboard, persona_keyboard, plan_confirmation_keyboard
from ze.telegram.session import ActiveSessionStore
from ze.telemetry.context import set_flow_context

log = get_logger(__name__)


class ZeBot:
    def __init__(
        self,
        bot: Bot,
        graph,
        workflow_graph,
        store: ActiveSessionStore,
        router,
        capability_gate,
        memory_store,
        persona_store,
        person_store,
        workflow_store,
        workflow_planner,
        openrouter_client,
        embedder,
        settings,
        transcription_client=None,
        translations: ProgressTranslations | None = None,
        pool=None,
        contact_channel_store=None,
        goal_store=None,
        goal_executor=None,
    ) -> None:
        self._bot = bot
        self._graph = graph
        self._workflow_graph = workflow_graph
        self._store = store
        self._router = router
        self._capability_gate = capability_gate
        self._memory_store = memory_store
        self._persona_store = persona_store
        self._person_store = person_store
        self._workflow_store = workflow_store
        self._workflow_planner = workflow_planner
        self._openrouter_client = openrouter_client
        self._embedder = embedder
        self._settings = settings
        self._transcription_client = transcription_client
        self._translations = translations
        self._pool = pool
        self._contact_channel_store = contact_channel_store
        self._goal_store = goal_store
        self._goal_executor = goal_executor

    # ── Public handlers ───────────────────────────────────────────────────────

    async def handle_message(self, message: Message) -> None:
        chat_id = message.chat.id
        text = message.text or ""
        bind_context(str(chat_id))

        try:
            if self._store.is_awaiting_edit(chat_id):
                await self._handle_edit_reply(chat_id, text)
                return

            gate_id = self._store.get_awaiting_goal_redirect(chat_id)
            if gate_id is not None and text:
                await self._handle_goal_redirect_reply(chat_id, gate_id, text)
                return

            if self._store.is_active(chat_id):
                await self._bot.send_message(chat_id, "A task is already in progress.")
                return

            if text == "/new":
                await self._reset_session(chat_id)
                await self._bot.send_message(chat_id, "Session reset. Starting fresh — I still remember what I know about you.")
                return

            if text == "/costs":
                summary = await costs_summary(self._pool)
                await self._bot.send_message(chat_id, summary, parse_mode="HTML")
                return

            if text == "/memory":
                summary = await memory_summary(self._pool)
                await self._bot.send_message(chat_id, summary, parse_mode="HTML")
                return

            if text == "/persona" or text.startswith("/persona "):
                await self._handle_persona_command(chat_id, text)
                return

            if text == "/contacts" or text.startswith("/contacts "):
                await self._handle_contacts_command(chat_id, text)
                return

            self._store.mark_active(chat_id)
            set_flow_context("user_message", str(chat_id))
            log.info("message_received", chat_id=chat_id)
            await self._run_graph(chat_id, self._make_initial_state(text, chat_id))
        finally:
            unbind_context()

    async def handle_voice(self, message: Message) -> None:
        chat_id = message.chat.id
        bind_context(str(chat_id))

        try:
            if self._store.is_active(chat_id):
                await self._bot.send_message(chat_id, "A task is already in progress.")
                return

            voice = message.voice or message.audio
            if not voice:
                return

            file = await self._bot.get_file(voice.file_id)
            buffer = BytesIO()
            await self._bot.download_file(file.file_path, buffer)
            audio_bytes = buffer.getvalue()

            duration = float(voice.duration) if voice.duration else None
            try:
                result = await self._transcription_client.transcribe(audio_bytes, "ogg", duration_seconds=duration)
            except Exception as exc:
                log.warning("transcription_failed", chat_id=chat_id, error=str(exc))
                await self._bot.send_message(chat_id, "Sorry, I couldn't transcribe that voice note.")
                return

            self._store.mark_active(chat_id)
            set_flow_context("user_message", str(chat_id))
            log.info("voice_received", chat_id=chat_id, text_len=len(result.text))

            state = self._make_initial_state(result.text, chat_id)
            state["input_modality"] = "voice"
            await self._run_graph(chat_id, state)
        finally:
            unbind_context()

    async def handle_photo(self, message: Message) -> None:
        chat_id = message.chat.id
        bind_context(str(chat_id))

        try:
            if self._store.is_active(chat_id):
                await self._bot.send_message(chat_id, "A task is already in progress.")
                return

            if not message.photo:
                return

            photo = message.photo[-1]
            if photo.file_size and photo.file_size > 8_388_608:
                await self._bot.send_message(chat_id, "Image is too large to process (max 8 MB).")
                return

            try:
                file = await self._bot.get_file(photo.file_id)
                buffer = BytesIO()
                await self._bot.download_file(file.file_path, buffer)
                image_bytes = buffer.getvalue()
            except Exception as exc:
                log.warning("image_download_failed", chat_id=chat_id, error=str(exc))
                raise ImageDownloadError(str(exc)) from exc

            self._store.mark_active(chat_id)
            set_flow_context("user_message", str(chat_id))
            log.info("photo_received", chat_id=chat_id, file_size=photo.file_size)

            caption = message.caption or ""
            state = self._make_initial_state(caption, chat_id)
            state["input_modality"] = "image"
            state["image_data"] = image_bytes
            state["image_mime"] = "image/jpeg"
            await self._run_graph(chat_id, state)
        finally:
            unbind_context()

    async def handle_callback(self, query: CallbackQuery) -> None:
        chat_id = query.message.chat.id
        data = query.data or ""
        bind_context(str(chat_id))

        try:
            if data.startswith("plan:"):
                await self._handle_plan_callback(chat_id, query)
                return

            if data.startswith("persona:"):
                await self._handle_persona_callback(chat_id, query)
                return

            if data.startswith("contact:"):
                await self._handle_contact_callback(chat_id, query)
                return

            if data.startswith("goal_plan:"):
                await self._handle_goal_plan_callback(chat_id, query)
                return

            if data.startswith("goal:"):
                await self._handle_goal_callback(chat_id, query)
                return

            if not data.startswith("confirm:"):
                await query.answer()
                return

            decision = data.split(":", 1)[1]
            await query.answer()

            # Remove keyboard from the confirmation message to prevent re-taps
            await query.message.edit_reply_markup(reply_markup=None)

            if decision == "edit":
                self._store.set_awaiting_edit(chat_id)
                await self._bot.send_message(
                    chat_id,
                    "Please reply with your edited version:",
                    reply_markup=ForceReply(selective=True),
                )
                return

            await self._resume_graph(chat_id, decision)
        finally:
            unbind_context()

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _reset_session(self, chat_id: int) -> None:
        config = self._make_config(chat_id)
        await self._graph.aupdate_state(config, {"messages": [], "last_active_at": None})
        self._store.clear_all(chat_id)
        log.info("session_reset", chat_id=chat_id)

    async def _handle_edit_reply(self, chat_id: int, text: str) -> None:
        self._store.clear_awaiting_edit(chat_id)
        self._store.cancel_confirm_task(chat_id)
        log.info("edit_reply_received", chat_id=chat_id)
        await self._resume_graph(chat_id, "edit", edit_content=text)

    async def _run_graph(self, chat_id: int, state: dict) -> None:
        config = self._make_config(chat_id)

        progress_queue: asyncio.Queue[str] = asyncio.Queue()
        message_bucket: list[int] = []

        if self._translations is not None:
            reporter = ProgressReporter(progress_queue, self._translations)
            config["configurable"]["reporter"] = reporter

            async def _progress_watcher() -> None:
                try:
                    while True:
                        text = await progress_queue.get()
                        try:
                            msg = await self._bot.send_message(chat_id, text)
                            message_bucket.append(msg.message_id)
                        except Exception:
                            pass
                except asyncio.CancelledError:
                    pass

            watcher_task: asyncio.Task | None = asyncio.create_task(_progress_watcher())
        else:
            watcher_task = None

        typing_task = asyncio.create_task(self._keep_typing(chat_id))
        try:
            final_state = await self._graph.ainvoke(state, config)
        except Exception as exc:
            log.exception("graph_error", chat_id=chat_id, error=str(exc))
            self._store.clear_all(chat_id)
            await self._bot.send_message(chat_id, "Something went wrong. Try again.")
            return
        finally:
            typing_task.cancel()
            if watcher_task is not None and not watcher_task.done():
                watcher_task.cancel()
                await asyncio.gather(watcher_task, return_exceptions=True)
            for msg_id in message_bucket:
                try:
                    await self._bot.delete_message(chat_id, msg_id)
                except Exception:
                    pass

        graph_state = await self._graph.aget_state(config)
        if graph_state.next:
            # Graph interrupted — needs confirmation
            result = final_state.get("agent_result")
            envelope = final_state.get("envelope")
            draft = result.response if result else ""
            agent = envelope.primary_agent if envelope else ""
            action = (
                envelope.subtasks[0].intent
                if envelope and envelope.subtasks
                else ""
            )
            await self._send_confirmation(chat_id, draft, agent, action, config)
        elif final_state.get("dynamic_plan_steps") is not None:
            steps = final_state["dynamic_plan_steps"]
            high_risk: list[int] = final_state.get("dynamic_plan_high_risk") or []
            if not high_risk:
                # All steps are autonomous — execute immediately
                await self._execute_dynamic_plan(chat_id, steps)
            else:
                # Show plan for user approval
                await self._send_plan_confirmation(chat_id, steps, high_risk)
        else:
            response = _extract_response(final_state)
            self._store.clear_active(chat_id)
            await self._send_response(chat_id, response)
            log.info("graph_complete", chat_id=chat_id)

    async def _resume_graph(
        self,
        chat_id: int,
        decision: str,
        edit_content: str | None = None,
    ) -> None:
        self._store.cancel_confirm_task(chat_id)
        config = self._store.get_pending_config(chat_id)
        if config is None:
            await self._bot.send_message(chat_id, "No pending confirmation.")
            return

        self._store.mark_active(chat_id)

        if decision == "no":
            self._store.clear_all(chat_id)
            await self._bot.send_message(chat_id, "Action cancelled.")
            return

        if decision == "edit" and edit_content is not None:
            await self._graph.aupdate_state(
                config,
                {"agent_result": None, "prompt": edit_content},
            )

        typing_task = asyncio.create_task(self._keep_typing(chat_id))
        try:
            final_state = await self._graph.ainvoke(None, config)
        except Exception as exc:
            log.exception("resume_error", chat_id=chat_id, error=str(exc))
            self._store.clear_all(chat_id)
            await self._bot.send_message(chat_id, "Something went wrong. Try again.")
            return
        finally:
            typing_task.cancel()

        self._store.clear_all(chat_id)
        response = _extract_response(final_state)
        await self._send_response(chat_id, response)
        log.info("resume_complete", chat_id=chat_id)

    async def _send_confirmation(
        self,
        chat_id: int,
        draft: str,
        agent: str,
        action: str,
        config: dict,
    ) -> None:
        text = (
            f"⚠️ <b>Confirmation required</b>\n\n"
            f"<b>Agent:</b> {_html.escape(agent)}\n"
            f"<b>Action:</b> {_html.escape(action)}\n\n"
            f"<b>Draft:</b>\n{md_to_html(draft)}"
        )
        await self._bot.send_message(
            chat_id,
            text,
            parse_mode="HTML",
            reply_markup=confirmation_keyboard(),
        )

        timeout_task = asyncio.create_task(
            self._confirmation_timeout(chat_id, config)
        )
        self._store.clear_active(chat_id)
        self._store.set_pending_confirmation(chat_id, config, timeout_task)
        log.info("awaiting_confirmation", chat_id=chat_id, agent=agent)

    async def _confirmation_timeout(self, chat_id: int, config: dict) -> None:
        try:
            await asyncio.sleep(self._settings.confirm_timeout_seconds)
            await self._graph.aupdate_state(config, {"error": "confirmation_expired"})
            self._store.clear_all(chat_id)
            await self._bot.send_message(
                chat_id,
                "⏱ Confirmation expired. The action was cancelled.",
            )
            log.info("confirmation_expired", chat_id=chat_id)
        except asyncio.CancelledError:
            pass

    async def _keep_typing(self, chat_id: int) -> None:
        try:
            while True:
                await self._bot.send_chat_action(chat_id, "typing")
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass

    async def _send_plan_confirmation(
        self,
        chat_id: int,
        steps: list,
        high_risk: list[int],
    ) -> None:
        lines = ["Ze will run the following steps:\n"]
        for i, step in enumerate(steps):
            marker = "⚠️ " if i in high_risk else ""
            lines.append(f"  {i + 1}. {marker}{step.task}")
        lines.append("\nProceed?")

        await self._bot.send_message(
            chat_id,
            "\n".join(lines),
            reply_markup=plan_confirmation_keyboard(),
        )

        timeout_task = asyncio.create_task(self._plan_approval_timeout(chat_id))
        self._store.clear_active(chat_id)
        self._store.set_pending_plan(chat_id, steps, timeout_task)
        log.info("awaiting_plan_approval", chat_id=chat_id, steps=len(steps), high_risk=high_risk)

    async def _handle_persona_command(self, chat_id: int, text: str) -> None:
        subcommand, args = parse_persona_command(text)

        if subcommand == "error":
            await self._bot.send_message(chat_id, args[0], parse_mode="HTML")
            return

        if subcommand == "profile":
            name = args[0]
            try:
                await self._persona_store.set_profile(name)
            except ValueError:
                profiles = self._persona_store.available_profiles()
                await self._bot.send_message(
                    chat_id,
                    f"Unknown profile <code>{_html.escape(name)}</code>. Available: {', '.join(profiles)}",
                    parse_mode="HTML",
                )
                return

        elif subcommand == "dial":
            dial_name, value_str = args
            try:
                await self._persona_store.set_dial(dial_name, float(value_str))
            except ValueError as exc:
                await self._bot.send_message(chat_id, _html.escape(str(exc)), parse_mode="HTML")
                return

        elif subcommand == "reset":
            await self._persona_store.reset_dials()

        summary = await persona_summary(self._persona_store)
        state = await self._persona_store.get_state()
        profiles = self._persona_store.available_profiles()
        keyboard = persona_keyboard(profiles, active=state.profile)
        await self._bot.send_message(chat_id, summary, parse_mode="HTML", reply_markup=keyboard)

    async def _handle_persona_callback(self, chat_id: int, query: CallbackQuery) -> None:
        data = query.data or ""
        # data format: "persona:profile:<name>"
        parts = data.split(":", 2)
        await query.answer()

        if len(parts) == 3 and parts[1] == "profile":
            name = parts[2]
            try:
                await self._persona_store.set_profile(name)
            except ValueError:
                return

        summary = await persona_summary(self._persona_store)
        state = await self._persona_store.get_state()
        profiles = self._persona_store.available_profiles()
        keyboard = persona_keyboard(profiles, active=state.profile)
        await query.message.edit_text(summary, parse_mode="HTML", reply_markup=keyboard)

    async def _handle_contacts_command(self, chat_id: int, text: str) -> None:
        query = text[len("/contacts"):].strip()
        if query:
            summary = await contacts_search(self._person_store, query)
        else:
            summary = await contacts_summary(self._person_store)
        await self._bot.send_message(chat_id, summary, parse_mode="HTML")

    async def _handle_contact_callback(self, chat_id: int, query: CallbackQuery) -> None:
        data = query.data or ""
        # data: "contact:confirm:<uuid>" or "contact:dismiss:<uuid>"
        parts = data.split(":", 2)
        await query.answer()
        await query.message.edit_reply_markup(reply_markup=None)

        if len(parts) != 3 or not self._person_store:
            return

        action, person_id_str = parts[1], parts[2]
        try:
            person_id = UUID(person_id_str)
        except ValueError:
            return

        if action == "confirm":
            try:
                person = await self._person_store.confirm(person_id)
                await self._bot.send_message(
                    chat_id,
                    f"✅ Added <b>{_html.escape(person.name)}</b> to your contacts.",
                    parse_mode="HTML",
                )
            except ValueError:
                await self._bot.send_message(chat_id, "Contact not found.")
        elif action == "dismiss":
            await self._person_store.dismiss(person_id)

    async def _handle_goal_plan_callback(self, chat_id: int, query: CallbackQuery) -> None:
        data = query.data or ""
        parts = data.split(":", 2)
        await query.answer()
        await query.message.edit_reply_markup(reply_markup=None)

        if len(parts) != 3 or not self._goal_executor or not self._goal_store:
            return

        action, goal_id_str = parts[1], parts[2]
        from uuid import UUID

        goal_id = UUID(goal_id_str)
        goal = await self._goal_store.get_goal(goal_id)

        if action == "yes":
            ok = await self._goal_executor.approve_plan(goal_id)
            if ok and goal:
                await self._bot.send_message(
                    chat_id,
                    f"✅ Goal <b>{_html.escape(goal.title)}</b> started.",
                    parse_mode="HTML",
                )
            else:
                await self._bot.send_message(chat_id, "That goal is no longer awaiting approval.")
        elif action == "no":
            ok = await self._goal_executor.reject_plan(goal_id)
            if ok and goal:
                await self._bot.send_message(
                    chat_id,
                    f"❌ Goal <b>{_html.escape(goal.title)}</b> cancelled.",
                    parse_mode="HTML",
                )
            else:
                await self._bot.send_message(chat_id, "That goal is no longer awaiting approval.")

    async def _handle_goal_callback(self, chat_id: int, query: CallbackQuery) -> None:
        data = query.data or ""
        # data: "goal:approve:<gate_id>" | "goal:stop:<gate_id>" | "goal:redirect:<gate_id>"
        parts = data.split(":", 2)
        await query.answer()
        await query.message.edit_reply_markup(reply_markup=None)

        if len(parts) != 3 or not self._goal_executor:
            return

        action, gate_id_str = parts[1], parts[2]

        if action == "approve":
            from uuid import UUID
            asyncio.create_task(self._goal_executor.handle_gate_approved(UUID(gate_id_str)))

        elif action == "stop":
            from uuid import UUID
            asyncio.create_task(self._goal_executor.handle_gate_stopped(UUID(gate_id_str)))

        elif action == "redirect":
            self._store.set_awaiting_goal_redirect(chat_id, gate_id_str)
            await self._bot.send_message(
                chat_id,
                "Send your new instructions for this goal:",
                reply_markup=ForceReply(selective=True),
            )

    async def _handle_goal_redirect_reply(self, chat_id: int, gate_id_str: str, text: str) -> None:
        self._store.clear_awaiting_goal_redirect(chat_id)
        if not self._goal_executor:
            return
        from uuid import UUID
        asyncio.create_task(self._goal_executor.handle_gate_redirected(UUID(gate_id_str), text))
        await self._bot.send_message(chat_id, "Got it — replanning and continuing.")

    async def _handle_plan_callback(self, chat_id: int, query: CallbackQuery) -> None:
        decision = (query.data or "").split(":", 1)[1]
        await query.answer()
        await query.message.edit_reply_markup(reply_markup=None)

        steps, timeout_task = self._store.get_pending_plan(chat_id)
        if timeout_task:
            timeout_task.cancel()

        if decision == "yes" and steps:
            self._store.cancel_plan_task(chat_id)
            self._store.mark_active(chat_id)
            asyncio.create_task(self._execute_dynamic_plan(chat_id, steps))
        else:
            self._store.cancel_plan_task(chat_id)
            self._store.clear_active(chat_id)
            await self._bot.send_message(
                chat_id,
                "Plan cancelled. What would you like to change?",
            )

    async def _execute_dynamic_plan(self, chat_id: int, steps: list) -> None:
        execution_id = await self._workflow_store.start_execution(None)
        thread_id = str(execution_id)
        config = self._make_workflow_config(thread_id)

        state = {
            "prompt": "",
            "session_id": str(chat_id),
            "session_overrides": {},
            "input_modality": "text",
            "image_data": None,
            "image_mime": None,
            "image_caption": None,
            "envelope": None,
            "memory_context": None,
            "agent_context": None,
            "gate_decision": None,
            "agent_result": None,
            "subtask_results": [],
            "pending_confirmation": False,
            "final_response": None,
            "error": None,
            "messages": [],
            "last_active_at": None,
            "workflow_id": None,
            "workflow_execution_id": execution_id,
            "workflow_steps": steps,
            "current_step_index": 0,
            "workflow_step_results": [],
            "dynamic_plan_steps": None,
            "dynamic_plan_high_risk": [],
        }

        typing_task = asyncio.create_task(self._keep_typing(chat_id))
        try:
            final_state = await self._workflow_graph.ainvoke(state, config)
        except Exception as exc:
            log.exception("dynamic_plan_exec_error", chat_id=chat_id, error=str(exc))
            self._store.clear_active(chat_id)
            await self._bot.send_message(chat_id, "Something went wrong executing the plan. Try again.")
            return
        finally:
            typing_task.cancel()

        response = _extract_response(final_state)
        self._store.clear_active(chat_id)
        await self._send_response(chat_id, response)
        log.info("dynamic_plan_complete", chat_id=chat_id, execution_id=str(execution_id))

    async def _plan_approval_timeout(self, chat_id: int) -> None:
        try:
            await asyncio.sleep(self._settings.confirm_timeout_seconds)
            self._store.cancel_plan_task(chat_id)
            self._store.clear_active(chat_id)
            await self._bot.send_message(
                chat_id,
                "⏱ Plan approval timed out. The plan was cancelled.",
            )
            log.info("plan_approval_expired", chat_id=chat_id)
        except asyncio.CancelledError:
            pass

    async def _send_response(self, chat_id: int, text: str) -> None:
        if not text:
            return
        html = md_to_html(text)
        for chunk in split_html(html):
            await self._bot.send_message(chat_id, chunk, parse_mode="HTML")

    async def invoke(self, prompt: str, session_id: str) -> dict:
        """Invoke the graph directly for eval/testing. Returns raw final state."""
        state = self._make_initial_state(prompt, session_id)
        config = {
            "configurable": {
                "thread_id": f"eval-{session_id}",
                "router": self._router,
                "capability_gate": self._capability_gate,
                "memory_store": self._memory_store,
                "persona_store": self._persona_store,
                "person_store": self._person_store,
                "openrouter_client": self._openrouter_client,
                "embedder": self._embedder,
                "settings": self._settings,
                "workflow_planner": self._workflow_planner,
                "contact_channel_store": self._contact_channel_store,
            }
        }
        return await self._graph.ainvoke(state, config)

    def _make_config(self, chat_id: int) -> dict:
        return {
            "configurable": {
                "thread_id": str(chat_id),
                "router": self._router,
                "capability_gate": self._capability_gate,
                "memory_store": self._memory_store,
                "persona_store": self._persona_store,
                "person_store": self._person_store,
                "openrouter_client": self._openrouter_client,
                "embedder": self._embedder,
                "settings": self._settings,
                "workflow_planner": self._workflow_planner,
                "contact_channel_store": self._contact_channel_store,
            }
        }

    def _make_workflow_config(self, thread_id: str) -> dict:
        return {
            "configurable": {
                "thread_id": thread_id,
                "router": self._router,
                "capability_gate": self._capability_gate,
                "memory_store": self._memory_store,
                "persona_store": self._persona_store,
                "openrouter_client": self._openrouter_client,
                "embedder": self._embedder,
                "settings": self._settings,
                "workflow_store": self._workflow_store,
            }
        }

    @staticmethod
    def _make_initial_state(prompt: str, chat_id: int | str) -> dict:
        return {
            "prompt": prompt,
            "session_id": str(chat_id),
            "session_overrides": {},
            "input_modality": "text",
            "image_data": None,
            "image_mime": None,
            "image_caption": None,
            "envelope": None,
            "memory_context": None,
            "agent_context": None,
            "gate_decision": None,
            "agent_result": None,
            "subtask_results": [],
            "pending_confirmation": False,
            "final_response": None,
            "error": None,
            "messages": [],
            "last_active_at": None,
            "workflow_id": None,
            "workflow_execution_id": None,
            "workflow_steps": None,
            "current_step_index": 0,
            "workflow_step_results": [],
            "dynamic_plan_steps": None,
            "dynamic_plan_high_risk": [],
        }


def _extract_response(state: dict) -> str:
    """Return the best available response text from a completed graph state."""
    if state.get("final_response"):
        return state["final_response"]
    result = state.get("agent_result")
    if result and result.response:
        return result.response
    return ""


