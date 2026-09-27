import { useEffect, useState } from "react";
import { fetchBrandPacks, fetchTemplates, uploadBrandPack, uploadTemplate } from "../lib/api";
import { AUTO_TEMPLATE_OPTION, NO_PACK_OPTION } from "../lib/constants";
import { errorMessage } from "../lib/format";
import type { BrandPack, TemplateInfo } from "../lib/types";

// Templates and brand packs known to the server, the user's current pick of
// each, and their uploads.
export function useLibrary() {
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
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

  function refreshTemplates(selectId?: string) {
    return fetchTemplates()
      .then((data) => {
        setTemplates(data.templates);
        if (selectId && data.templates.some((t) => t.id === selectId)) {
          setTemplateId(selectId);
        } else if (
          templateId !== AUTO_TEMPLATE_OPTION &&
          data.templates.length > 0 &&
          !data.templates.some((t) => t.id === templateId)
        ) {
          setTemplateId(data.templates[0]?.id ?? templateId);
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

  async function handlePackUpload(file: File | undefined) {
    if (!file) return;
    setPackError(null);
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setPackError("Бренд-пакет загружается одним .zip-архивом");
      return;
    }
    const suggested = file.name.replace(/\.[^.]+$/, "");
    const name = window.prompt("Название бренд-пакета", suggested);
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
      const { id } = await uploadTemplate(file);
      await refreshTemplates(id);
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
  };
}

export type Library = ReturnType<typeof useLibrary>;
