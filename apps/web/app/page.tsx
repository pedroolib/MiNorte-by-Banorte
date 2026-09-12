import Dashboard from "./cards/dashboard";

/**
 * `/` — vista final curada (hoy: el dashboard con selección de hoy,
 * filtros y prioridades). Renderiza vía componentes registrados;
 * a futuro la IA elegirá el subconjunto (spec #22).
 */
export default function Page() {
  return <Dashboard />;
}
