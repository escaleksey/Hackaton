import { render, screen } from "@testing-library/react";

import { ContractIssuesPanel } from "./ContractIssuesPanel";

describe("ContractIssuesPanel", () => {
  it("renders issue details, warning banner, and download button for docx", () => {
    render(
      <ContractIssuesPanel
        warnings={[
          {
            code: "llm_insufficient_quota",
            message: "Показаны только локальные rule-based проверки.",
          },
        ]}
        issues={[
          {
            paragraph_index: 2,
            fragment: "с 25.03.2023 по 02.02.2023",
            type: "DATE_CONFLICT",
            severity: "high",
            confidence: "high",
            explanation: "Дата окончания раньше даты начала.",
            suggestion: "Уточнить дату окончания договора.",
          },
        ]}
        isDocx
        onDownloadMarked={() => {}}
        isDownloading={false}
      />,
    );

    expect(screen.getByText("Найденные замечания")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Показаны только локальные rule-based проверки.",
    );
    expect(screen.getByText("Абзац #2")).toBeInTheDocument();
    expect(screen.getByText("Тип: DATE_CONFLICT")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Скачать размеченный DOCX" }),
    ).toBeInTheDocument();
  });
});
