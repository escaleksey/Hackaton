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
  onDownloadMarked,
  isDownloading,
}) {
  return (
    <section className="card issues-panel">
      <div className="issues-panel__header">
        <div>
          <h2>Найденные замечания</h2>
          <p>Сервис возвращает JSON со списком проблем и размеченный документ для скачивания.</p>
        </div>

        {isDocx ? (
          <button className="button button--primary" type="button" onClick={onDownloadMarked} disabled={isDownloading}>
            {isDownloading ? "Готовим DOCX..." : "Скачать размеченный DOCX"}
          </button>
        ) : null}
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
            </article>
          ))}
        </div>
      ) : (
        <p className="issues-panel__empty">
          По заданным правилам замечаний не найдено. В JSON сервис вернул пустой список `issues`.
        </p>
      )}
    </section>
  );
}
