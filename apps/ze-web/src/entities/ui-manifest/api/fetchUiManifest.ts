import { getUiManifest } from "@ze/client";

export async function fetchUiManifest() {
  const { data, error } = await getUiManifest();
  if (error || !data) {
    throw new Error("Failed to load UI manifest");
  }
  return data;
}
