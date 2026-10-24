export const MAX_PHOTO_BYTES = 2 * 1024 * 1024;

const PHOTO_STORAGE_PREFIX = "provenancelab.photo-source.v1.";
const SUPPORTED_PHOTO_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export interface PhotoSourceDraft {
  filename: string;
  mediaType: string;
  fileSize: number;
  sha256: string;
  dataUrl: string;
}

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("The selected image could not be read."));
    reader.readAsDataURL(file);
  });
}

async function sha256(file: File): Promise<string> {
  const bytes = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function createPhotoSource(file: File): Promise<PhotoSourceDraft> {
  if (!SUPPORTED_PHOTO_TYPES.has(file.type)) {
    throw new Error("Choose a PNG, JPEG, or WebP image.");
  }
  if (file.size > MAX_PHOTO_BYTES) {
    throw new Error("Choose an image smaller than 2 MB so it can be preserved in this browser session.");
  }

  const [dataUrl, fileHash] = await Promise.all([readAsDataUrl(file), sha256(file)]);
  const photo = {
    filename: file.name,
    mediaType: file.type,
    fileSize: file.size,
    sha256: fileHash,
    dataUrl,
  };

  try {
    sessionStorage.setItem(`${PHOTO_STORAGE_PREFIX}${fileHash}`, JSON.stringify(photo));
  } catch {
    throw new Error("The image could not be preserved because this browser session is out of storage space.");
  }
  return photo;
}

export function loadPhotoSource(fileHash?: string): PhotoSourceDraft | null {
  if (!fileHash) return null;
  const raw = sessionStorage.getItem(`${PHOTO_STORAGE_PREFIX}${fileHash}`);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<PhotoSourceDraft>;
    if (
      typeof parsed.filename !== "string"
      || typeof parsed.mediaType !== "string"
      || typeof parsed.fileSize !== "number"
      || parsed.sha256 !== fileHash
      || typeof parsed.dataUrl !== "string"
    ) {
      return null;
    }
    return parsed as PhotoSourceDraft;
  } catch {
    return null;
  }
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}
