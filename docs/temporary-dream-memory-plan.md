# Temporary Plan: Ze Dreaming / Offline Memory

> Draft-only note. This is not a committed spec.
> Purpose: define what we need to research, what architecture choices we must make, and what must be planned before implementation.

## Goal

Make Ze run an offline "dream" phase when it is not in use. The phase should improve memory quality, abstraction, and robustness without letting synthetic outputs overwrite trusted memory.

## What we need to research

### Neuroscience and cognitive science

- What brain research most strongly supports:
  - replay of recent experience
  - memory consolidation during sleep
  - context reinstatement
  - REM-like recombination or imagination
- Which findings are causal vs correlational.
- Which parts are likely useful metaphors and which parts are operationally testable.
- Whether there is evidence for separate functions for NREM-like replay and REM-like synthesis.
- What sleep research says about:
  - consolidation
  - pruning/forgetting
  - generalization
  - emotional regulation

### Machine learning analogues

- Experience replay and generative replay.
- Continual learning and catastrophic forgetting.
- Offline self-training and self-distillation.
- Model-based imagination / synthetic rollouts.
- Critic-based filtering of synthetic outputs.

### Product and safety

- What user value this feature should produce first:
  - better memory retention
  - better summarization
  - better generalization
  - better self-correction
  - better creative recombination
- How to keep dream outputs from being mistaken for facts.
- How to present dreaming to the user without making the system look random or unreliable.

## Architecture questions to answer

### Memory model

- What memory layers should exist?
  - episodic
  - semantic
  - procedural / policy
  - dream buffer
- What data goes into each layer?
- What gets written immediately vs only after validation?
- What provenance is required for every memory item?

### Dream pipeline

- What events trigger dreaming?
  - nightly scheduler
  - inactivity window
  - memory pressure threshold
  - user-defined schedule
- What happens in each phase?
  - capture
  - replay
  - compression
  - generation of variants
  - critique / scoring
  - promotion or rejection
- How much of the pipeline is rule-based vs model-based?

### Validation and trust

- What makes a dream output acceptable?
- What confidence threshold is needed to promote a synthetic insight?
- Should dream outputs ever update:
  - memory summaries
  - fact store
  - procedures
  - task plans
- Do we need a human review surface for some categories?

### Scheduling and compute

- How expensive can the dream phase be?
- Does it run on local models, remote models, or both?
- How long can it run before it becomes too costly or too slow?
- Do we need incremental nightly runs or a full replay pass?

### Observability

- What should be logged?
  - inputs
  - sampled memories
  - synthetic outputs
  - scoring decisions
  - promoted changes
- How do we inspect why a dream result was accepted or rejected?
- Do we want a visible "dream journal" for the user? (yes)

## What we need to plan before implementation

### Phase definition

- Define the first valuable version.
- Define what is explicitly out of scope.
- Decide whether the first version is:
  - consolidation only
  - consolidation + synthetic recombination
  - full replay + dream + critic loop

### Integration strategy

- Prefer the scalable architecture that best serves the feature, even if it requires changing the current core.
- Do not preserve an existing boundary just because the codebase already has it.
- The single-user model gives us freedom to redesign for clarity and long-term maintainability.
- First ask: what architecture would we choose if we were starting with this feature today?
- Only avoid a refactor if the existing path is already clean and scalable.
- If a core change is needed, make it deliberate and minimal, but do not let "minimal churn" override the better design.

### Success metrics

- Memory retention over time.
- Reduction in duplicate or stale memory.
- Improvement on retrieval quality.
- Improvement on task completion or self-correction.
- User-facing clarity of the feature.

### Data contracts

- Define the schema for:
  - captured episodes
  - replay samples
  - dream artifacts
  - critic scores
  - promoted memory updates
- Define provenance fields and timestamps.
- Define which outputs are immutable.

### Integration points

- Where the dream job lives in the current system.
- Which package owns the logic.
- How the scheduler invokes it.
- How results are written back into memory.
- How the web UI, logs, or admin tools expose it.

### Failure modes

- Synthetic memory being treated as fact.
- Dream loop amplifying a wrong pattern.
- Overwriting stable memory with low-quality output.
- Cost blowups from too much offline generation.
- Drift between dream summaries and actual source episodes.

## Proposed implementation sequence

1. Decide the target architecture for dreaming as if we were designing it from scratch.
2. Map the current core boundaries and identify where they help or hinder that target.
3. Choose whether the current architecture should be extended, adapted, or refactored.
4. Stabilize the memory model and identify which stored records are eligible for dreaming.
5. Build a replay-only offline job with no synthetic generation.
6. Add a dream buffer for variants and counterfactuals.
7. Add a critic layer to score and filter outputs.
8. Promote only validated outputs into long-term memory or procedures.
9. Add observability and a user-visible dream journal.

## Investigation phases

### Phase 0: Core fit check

- Inventory the current scheduler, memory write path, and workflow orchestration.
- Identify where the present architecture is elegant enough to keep.
- Identify where it is only "easy" because it already exists.
- Decide whether the feature can be isolated cleanly or whether a structural change would produce a better long-term design.

### Phase 1: Minimal integration design

- Define the best viable contract between dreaming and existing memory systems.
- Decide which existing tables, jobs, or APIs can be reused without constraining the design.
- Write down what should stay stable and what should be redesigned.

### Phase 2: Narrow refactor assessment

- If reuse is not enough, identify the refactor that gives the cleanest scalable shape.
- Separate "required for correctness" from "preferred for maintainability."
- Avoid unrelated cleanup, but do not reject necessary architecture work just to avoid touching core.

### Phase 3: Implementation planning

- Convert the chosen integration path into concrete tasks.
- Assign ownership for any core touchpoints.
- Plan validation, observability, and rollback.

## Questions to resolve next

- What exact outcome is the first release optimizing for?
- What memories are allowed into the dream buffer?
- How do we score a "good" dream?
- What is the minimum acceptable safety boundary?
- Do we want the system to feel biological, or simply useful?
