import { createBrowserRouter } from "react-router-dom";
import { AppLayout } from "@/layouts/AppLayout";
import { ChatPage } from "@/pages/ChatPage";
import { GoalsPage } from "@/pages/GoalsPage";
import { RemindersPage } from "@/pages/RemindersPage";
import { ContactsPage } from "@/pages/ContactsPage";
import { CostsPage } from "@/pages/CostsPage";
import { NewsPage } from "@/pages/NewsPage";
import { SettingsPage } from "@/pages/SettingsPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <ChatPage /> },
      { path: "goals", element: <GoalsPage /> },
      { path: "reminders", element: <RemindersPage /> },
      { path: "contacts", element: <ContactsPage /> },
      { path: "costs", element: <CostsPage /> },
      { path: "news", element: <NewsPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);
