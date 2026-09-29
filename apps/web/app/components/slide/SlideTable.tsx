import { EMU_PER_PT, runText } from "../../lib/slideColors";
import type { TableShape } from "../../lib/types";

export function SlideTable({ shape, scale }: { shape: TableShape; scale: number }) {
  return (
    <table
      style={{
        width: "100%",
        height: "100%",
        borderCollapse: "collapse",
        tableLayout: "fixed",
        fontSize: `${Math.max(7, 11 * scale * EMU_PER_PT)}px`,
      }}
    >
      <tbody>
        {shape.rows.map((row, ri) => (
          <tr key={ri}>
            {row.map((cell, ci) => (
              <td
                key={ci}
                style={{
                  border: "1px solid rgba(0,0,0,0.15)",
                  padding: "2px 4px",
                  color: "var(--fill-2)",
                  fontWeight: ri === 0 ? 700 : 400,
                  overflow: "hidden",
                  whiteSpace: "nowrap",
                  textOverflow: "ellipsis",
                }}
              >
                {cell.paragraphs.map((p) => runText(p.runs)).join(" ")}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
