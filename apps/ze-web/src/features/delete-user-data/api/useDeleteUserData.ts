import { createDeleteIntent, deleteData } from "@myguyze/ze-client";
import { useState } from "react";
import { clearConfig } from "@/shared/config";

export function useDeleteUserData() {
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function deleteAllData() {
    setDeleting(true);
    setDeleteError(null);
    try {
      const { data: intent } = await createDeleteIntent();
      if (!intent) throw new Error("Failed to create delete intent");
      await deleteData({ body: { confirmation_token: intent.confirmation_token } });
      clearConfig();
      window.location.reload();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Deletion failed");
    } finally {
      setDeleting(false);
    }
  }

  function clearDeleteError() {
    setDeleteError(null);
  }

  return { deleting, deleteError, deleteAllData, clearDeleteError };
}
