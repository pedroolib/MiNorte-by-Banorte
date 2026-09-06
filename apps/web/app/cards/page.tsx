import { DynamicUI } from "@/components/registry";
import { CATALOG } from "@/lib/catalog-fixtures";

/**
 * /cards — GALERÍA del catálogo (muestrario, NO es el UI final).
 * Renderiza cada componente registrado con props fixture.
 * Si agregas una entrada al registry sin fixture aquí, el test
 * anti-drift lo detecta.
 */
export default function CardsGallery() {
  return (
    <main className="mx-auto max-w-5xl space-y-8 p-6">
      <header>
        <p className="text-xs font-bold uppercase tracking-widest text-neutral-500">
          Muestrario — no es el UI final
        </p>
        <h1 className="text-2xl font-bold">Catálogo de tarjetas ({CATALOG.length})</h1>
        <p className="text-sm text-neutral-500">
          Totales ancla verificados contra el backend; desgloses y series
          marcados como muestra son ilustrativos.
        </p>
      </header>
      {CATALOG.map((entry) => (
        <section key={entry.component} className="space-y-2">
          <div className="flex items-baseline gap-3">
            <h2 className="font-mono text-sm font-bold">{entry.component}</h2>
            <span className="text-xs text-neutral-500">{entry.title}</span>
          </div>
          <p className="font-mono text-[11px] text-neutral-400">{entry.source}</p>
          <DynamicUI schema={{ component: entry.component, props: entry.props } as any} />
          <details className="text-xs text-neutral-500">
            <summary className="cursor-pointer">props</summary>
            <pre className="overflow-auto rounded bg-neutral-50 p-2">
              {JSON.stringify(entry.props, null, 2)}
            </pre>
          </details>
        </section>
      ))}
    </main>
  );
}
