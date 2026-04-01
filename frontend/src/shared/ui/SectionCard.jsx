export function SectionCard({ title, description, children }) {
  return (
    <section className="card">
      {title ? <h2>{title}</h2> : null}
      {description ? <p>{description}</p> : null}
      {children}
    </section>
  );
}
