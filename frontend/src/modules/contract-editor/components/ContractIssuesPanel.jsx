function severityLabel(severity) {
  if (severity === "high") {
    return "Высокая";
  }

  if (severity === "medium") {
    return "Средняя";
  }

  return "Низкая";
}

export function ContractIssuesPanel({
  warnings = [],
  issues,
  isDocx,
  onApplyIssue,
  onApplyAllSuggestions,
  onDownloadMarked,
  isDownloading,
}) {
  const applicableIssues = issues.filter((issue) => issue.fragment && issue.replacement);

  return (
    <section className="card issues-panel">
      <div className="issues-panel__header">
        <div>
          <h2>Найденные замечания</h2>
        </div>

        <div className="issues-panel__actions">
          {applicableIssues.length ? (
            <button className="button button--secondary" type="button" onClick={onApplyAllSuggestions}>
              Применить все автозамены
            </button>
          ) : null}
          {isDocx ? (
            <button
              className="button button--primary"
              type="button"
              onClick={onDownloadMarked}
              disabled={isDownloading}
            >
              {isDownloading ? "Готовим DOCX..." : "Скачать размеченный DOCX"}
            </button>
          ) : null}
        </div>
      </div>

      {warnings.length ? (
        <div className="issues-panel__warnings" role="alert">
          {warnings.map((warning) => (
            <p key={`${warning.code}-${warning.message}`}>{warning.message}</p>
          ))}
        </div>
      ) : null}

      {issues.length ? (
        <div className="issues-list">
          {issues.map((issue, index) => (
            <article className="issue-card" key={`${issue.paragraph_index}-${issue.type}-${index}`}>
              <div className="issue-card__meta">
                <span className={`severity-pill severity-pill--${issue.severity}`}>
                  {severityLabel(issue.severity)}
                </span>
                <span>Абзац #{issue.paragraph_index}</span>
                <span>Тип: {issue.type}</span>
                <span>Уверенность: {issue.confidence}</span>
              </div>

              <p className="issue-card__fragment">«{issue.fragment}»</p>
              <p>
                <strong>Пояснение:</strong> {issue.explanation}
              </p>
              <p>
                <strong>Рекомендуемая замена:</strong> {issue.suggestion}
              </p>
              {issue.replacement ? (
                <div className="issue-card__actions">
                  <p className="issue-card__replacement">
                    <strong>Автозамена:</strong> {issue.replacement}
                  </p>
                  <button className="button button--secondary" type="button" onClick={() => onApplyIssue?.(issue)}>
                    Применить замену
                  </button>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <p className="issues-panel__empty">
          По текущим правилам замечаний не найдено. Сервис вернул пустой список `issues`
        </p>
      )}
    </section>
  );
}
