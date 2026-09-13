/**
 * Isotipo oficial Banorte (mismo trazo que `app/icon.svg`, el favicon del
 * tab). Rojo institucional #EC1C2D, sin recolorear: es marca registrada.
 */
export function BanorteMark({ className = "block h-9 w-auto shrink-0" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 382 235.2"
      role="img"
      aria-label="Banorte"
      className={className}
    >
      <g fill="#EC1C2D" transform="matrix(3.2,0,0,3.2,-65.6,-911.04)">
        <path d="m 84.5,284.7 c -28.5,0 -51.6,7.5 -51.6,16.8 0,7.8 16.1,14.3 38,16.2 l 9,-27.7 1.6,28.2 c 1,0 2,0 3.1,0 28.5,0 51.6,-7.5 51.6,-16.8 -0.1,-9.1 -23.2,-16.7 -51.7,-16.7" />
        <path d="m 70.6,318.7 c -27.8,0.3 -50.1,9.1 -50.1,20 0,9.2 15.8,16.9 37.4,19.3 z" />
        <path d="m 81.4,319 2.2,39.2 c 22.9,-2 39.9,-10 39.9,-19.5 0.1,-9.8 -18.1,-18 -42.1,-19.7" />
      </g>
    </svg>
  );
}
