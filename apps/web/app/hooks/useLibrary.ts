import { useEffect, useState } from "react";
import { fetchBrandPacks, fetchTemplates, uploadBrandPack, uploadTemplate } from "../lib/api";
import { AUTO_TEMPLATE_OPTION, NO_PACK_OPTION } from "../lib/constants";
import { errorMessage } from "../lib/format";
import type { BrandPack, TemplateInfo } from "../lib/types";

// Templates and brand packs known to the server, the user's current pick of
// each, and their uploads.
export function useLibrary() {
  const [libraryTemplates, setLibraryTemplates] = useState<TemplateInfo[]>([]);
  // This browser's own uploads (POST /api/templates): the server deliberately
  // never lists these back in GET /api/templates — they're not part of the
  // shared library, just this session's private pick — so they live only
  // here, merged into `templates` below.
  const [uploadedTemplates, setUploadedTemplates] = useState<TemplateInfo[]>([]);
  const templates = [...libraryTemplates, ...uploadedTemplates];
  // False only once we hear back from the server; true (optimistic) until then,
  // so the picker doesn't flash a fallback before the first response arrives.
  const [rendererAvailable, setRendererAvailable] = useState(true);
  const [templateId, setTemplateId] = useState(AUTO_TEMPLATE_OPTION);
  // Whether the user has made a template choice at all ("Авто" included) —
  // the sidebar says "Выбрать шаблон" and generation reminds them until then.
  const [templateChosen, setTemplateChosen] = useState(false);

  function chooseTemplate(id: string) {
    setTemplateId(id);
    setTemplateChosen(true);
  }
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [packs, setPacks] = useState<BrandPack[]>([]);
  const [packId, setPackId] = useState(NO_PACK_OPTION);
  const [packError, setPackError] = useState<string | null>(null);

  const [syncing, setSyncing] = useState(false);

  function refreshTemplates(selectId?: string) {
    return fetchTemplates()
      .then((data) => {
        setLibraryTemplates(data.templates);
        setRendererAvailable(data.renderer_available);
        setSyncing(Boolean(data.syncing));
        // A private upload never appears in `data.templates` (the server
        // never lists it) — count it as known too, so this refresh (e.g.
        // the brand-pack poll below) can't mistake it for one that vanished
        // and reset the selection away from it.
        const known = [...data.templates, ...uploadedTemplates];
        if (selectId && known.some((t) => t.id === selectId)) {
          setTemplateId(selectId);
        } else if (
          templateId !== AUTO_TEMPLATE_OPTION &&
          known.length > 0 &&
          !known.some((t) => t.id === templateId)
        ) {
          setTemplateId(known[0]?.id ?? templateId);
        }
      })
      .catch(() => {
        // No API server yet, or it's down — the composer still works once
        // it comes up; the sidebar just falls back to the default id below.
      });
  }

  function refreshPacks(selectId?: string) {
    return fetchBrandPacks()
      .then((data) => {
        setPacks(data.packs);
        if (selectId) setPackId(selectId);
      })
      .catch(() => {});
  }

  useEffect(() => {
    void refreshTemplates();
    void refreshPacks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Preset templates download in the background, and their previews render as they
  // land: keep the list fresh until that is done.
  const preparing = syncing || libraryTemplates.some((t) => !t.previews);
  useEffect(() => {
    if (!preparing) return;
    const interval = setInterval(() => void refreshTemplates().catch(() => undefined), 4000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preparing]);

  // A pack builds in the background on the server (LLM extraction over its
  // documents) — poll until none is still building, then pick up its
  // templates in the template list too.
  const anyPackBuilding = packs.some((p) => p.status === "building");
  useEffect(() => {
    if (!anyPackBuilding) return;
    const interval = setInterval(() => {
      void refreshPacks().then(() => refreshTemplates());
    }, 3000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anyPackBuilding]);

  // `name` given: upload under it; otherwise ask (defaulting to the file name).
  async function handlePackUpload(file: File | undefined, name?: string) {
    if (!file) return;
    setPackError(null);
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setPackError("Бренд-пакет загружается одним .zip-архивом");
      return;
    }
    if (!name) {
      const suggested = file.name.replace(/\.[^.]+$/, "");
      name = window.prompt("Название бренд-пакета", suggested) ?? "";
    }
    if (!name) return;
    try {
      const { id } = await uploadBrandPack(name, file);
      await refreshPacks(id);
      await refreshTemplates();
    } catch (e) {
      setPackError(errorMessage(e));
    }
  }

  async function handleTemplateUpload(file: File) {
    setUploadError(null);
    setUploading(true);
    try {
      const { id, label } = await uploadTemplate(file);
      // Select it directly — the server will never list a private upload
      // back in GET /api/templates, so there's nothing to refresh here.
      setUploadedTemplates((prev) => [...prev, { id, label }]);
      setTemplateId(id);
      setTemplateChosen(true);
    } catch (e) {
      setUploadError(errorMessage(e));
    } finally {
      setUploading(false);
    }
  }

  function selectPack(id: string) {
    setPackId(id);
    // A pack brings its own template — let the server pick it.
    setTemplateId(AUTO_TEMPLATE_OPTION);
  }

  return {
    templates,
    templateId,
    setTemplateId,
    uploading,
    uploadError,
    handleTemplateUpload,
    packs,
    packId,
    selectPack,
    packError,
    anyPackBuilding,
    handlePackUpload,
    refreshTemplates,
    templateChosen,
    chooseTemplate,
    rendererAvailable,
  };
}

export type Library = ReturnType<typeof useLibrary>;
