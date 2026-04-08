import { useState } from "react";

import { ContractEditor } from "../modules/contract-editor/components/ContractEditor";
import { ContractIssuesPanel } from "../modules/contract-editor/components/ContractIssuesPanel";
import { ContractUploadForm } from "../modules/contract-editor/components/ContractUploadForm";
import { downloadContract, saveContract, uploadContract } from "../shared/api/contractsApi";
import { SectionCard } from "../shared/ui/SectionCard";

function triggerBrowserDownload(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

function replaceFirstOccurrence(text, search, replacement) {
  if (!text || !search || replacement == null) {
    return { text, changed: false };
  }

  const index = text.indexOf(search);
  if (index < 0) {
    return { text, changed: false };
  }

  return {
    text: `${text.slice(0, index)}${replacement}${text.slice(index + search.length)}`,
    changed: true,
  };
}

function applyIssueToPages(pages, issue) {
  let changed = false;

  const nextPages = pages.map((page) => ({
    ...page,
    blocks: page.blocks.map((block) => {
      if (changed) {
        return block;
      }

      const blockText = block.runs?.map((run) => run.text ?? "").join("") ?? "";
      const replacementResult = replaceFirstOccurrence(blockText, issue.fragment, issue.replacement);

      if (!replacementResult.changed) {
        return block;
      }

      changed = true;
      const templateRun = block.runs?.[0] ?? {};

      return {
        ...block,
        runs: [
          {
            ...templateRun,
            text: replacementResult.text,
            highlight_color: null,
          },
        ],
      };
    }),
  }));

  return { pages: nextPages, changed };
}

export function ContractWorkspacePage() {
  const [contract, setContract] = useState(null);
  const [correctedText, setCorrectedText] = useState("");
  const [correctedPages, setCorrectedPages] = useState([]);
  const [issues, setIssues] = useState([]);
  const [warnings, setWarnings] = useState([]);
  const [selectedPageIndex, setSelectedPageIndex] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isMarkedDownloading, setIsMarkedDownloading] = useState(false);

  const clearMessages = () => {
    setStatusMessage("");
    setErrorMessage("");
  };

  const syncDraftState = (draft) => {
    setContract(draft);
    setCorrectedText(draft.corrected_text);
    setCorrectedPages(draft.corrected_pages ?? []);
    setIssues(draft.issues ?? []);
    setWarnings(draft.warnings ?? []);
    setSelectedPageIndex(0);
  };

  const handleUpload = async ({ file, text }) => {
    setIsLoading(true);
    clearMessages();

    try {
      const draft = await uploadContract({ file, text });
      syncDraftState(draft);
      setStatusMessage(`Документ проанализирован. Найдено замечаний: ${draft.issues?.length ?? 0}`);
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async () => {
    if (!contract) {
      return;
    }

    setIsSaving(true);
    clearMessages();

    try {
      const updatedDraft = await saveContract(contract.id, {
        correctedText: contract.source_format === "docx" ? undefined : correctedText,
        correctedPages: contract.source_format === "docx" ? correctedPages : undefined,
      });
      syncDraftState(updatedDraft);
      setStatusMessage("Правки сохранены на сервере");
      return updatedDraft;
    } catch (error) {
      setErrorMessage(error.message);
      return null;
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveAndDownload = async () => {
    if (!contract) {
      return;
    }

    setIsDownloading(true);
    clearMessages();

    try {
      const updatedDraft = await saveContract(contract.id, {
        correctedText: contract.source_format === "docx" ? undefined : correctedText,
        correctedPages: contract.source_format === "docx" ? correctedPages : undefined,
      });
      syncDraftState(updatedDraft);

      const { blob, fileName } = await downloadContract(contract.id);
      triggerBrowserDownload(blob, fileName);
      setStatusMessage("Документ сохранен и отправлен на скачивание");
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsDownloading(false);
    }
  };

  const handleDownloadMarked = async () => {
    if (!contract) {
      return;
    }

    setIsMarkedDownloading(true);
    clearMessages();

    try {
      const { blob, fileName } = await downloadContract(contract.id);
      triggerBrowserDownload(blob, fileName);
      setStatusMessage("Размеченный документ отправлен на скачивание");
    } catch (error) {
      setErrorMessage(error.message);
    } finally {
      setIsMarkedDownloading(false);
    }
  };

  const handleDocxPageChange = (nextPage) => {
    setCorrectedPages((currentPages) =>
      currentPages.map((page, pageIndex) => {
        if (pageIndex !== selectedPageIndex) {
          return page;
        }

        return {
          ...page,
          ...nextPage,
        };
      }),
    );
  };

  const handleApplyIssue = (issue) => {
    if (!issue?.fragment || !issue?.replacement) {
      return;
    }

    clearMessages();

    if (contract?.source_format === "docx") {
      const { pages, changed } = applyIssueToPages(correctedPages, issue);
      if (!changed) {
        setErrorMessage("Не удалось автоматически применить замену в DOCX. Проверьте формулировку вручную");
        return;
      }

      setCorrectedPages(pages);
      setStatusMessage(`Замена применена: «${issue.fragment}» → «${issue.replacement}».`);
      return;
    }

    const replacementResult = replaceFirstOccurrence(correctedText, issue.fragment, issue.replacement);
    if (!replacementResult.changed) {
      setErrorMessage("Не удалось автоматически применить замену. Проверьте текст договора вручную");
      return;
    }

    setCorrectedText(replacementResult.text);
    setStatusMessage(`Замена применена: «${issue.fragment}» → «${issue.replacement}»`);
  };

  const handleApplyAllSuggestions = () => {
    const applicableIssues = issues.filter((issue) => issue.fragment && issue.replacement);
    if (!applicableIssues.length) {
      return;
    }

    clearMessages();

    if (contract?.source_format === "docx") {
      let nextPages = correctedPages;
      let appliedCount = 0;

      applicableIssues.forEach((issue) => {
        const result = applyIssueToPages(nextPages, issue);
        nextPages = result.pages;
        if (result.changed) {
          appliedCount += 1;
        }
      });

      setCorrectedPages(nextPages);
      setStatusMessage(
        appliedCount
          ? `Автозамены применены: ${appliedCount}. Документ можно сразу сохранить и скачать`
          : "Автозамены не применились автоматически. Проверьте формулировки вручную",
      );
      return;
    }

    let nextText = correctedText;
    let appliedCount = 0;

    applicableIssues.forEach((issue) => {
      const result = replaceFirstOccurrence(nextText, issue.fragment, issue.replacement);
      nextText = result.text;
      if (result.changed) {
        appliedCount += 1;
      }
    });

    setCorrectedText(nextText);
    setStatusMessage(
      appliedCount
        ? `Автозамены применены: ${appliedCount}. Текст готов к сохранению и скачиванию`
        : "Автозамены не применились автоматически. Проверьте формулировки вручную",
    );
  };

  return (
    <div className="page-shell">
      <div className="page">
        <header className="hero">
          <h1>Сервис анализа и разметки договоров</h1>
          <p>
            Загружайте `.docx` или `.txt` и получайте список логических противоречий,
            ошибок в употреблении терминов и противоречий в датах 
          </p>
        </header>

        <div className="workspace-grid">
          <div>
            <ContractUploadForm onSubmit={handleUpload} isLoading={isLoading} />
          </div>

          <div>
            {statusMessage ? <div className="status status--info">{statusMessage}</div> : null}
            {errorMessage ? <div className="status status--error">{errorMessage}</div> : null}

            {contract ? (
              <>
                <ContractIssuesPanel
                  issues={issues}
                  warnings={warnings}
                  isDocx={contract.source_format === "docx"}
                  onApplyIssue={handleApplyIssue}
                  onApplyAllSuggestions={handleApplyAllSuggestions}
                  onDownloadMarked={handleDownloadMarked}
                  isDownloading={isMarkedDownloading}
                />
                <ContractEditor
                  contract={contract}
                  correctedText={correctedText}
                  correctedPages={correctedPages}
                  selectedPageIndex={selectedPageIndex}
                  onSelectedPageChange={setSelectedPageIndex}
                  onCorrectedTextChange={setCorrectedText}
                  onDocxPageTextChange={handleDocxPageChange}
                  onSave={handleSave}
                  onSaveAndDownload={handleSaveAndDownload}
                  isSaving={isSaving}
                  isDownloading={isDownloading}
                />
              </>
            ) : (
              <SectionCard
                title="Редактор пока пуст"
                description="После загрузки договора здесь появятся замечания, разметка и редактируемая версия документа"
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
