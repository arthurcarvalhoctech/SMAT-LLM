import { groundTruthLabel } from "@/lib/format";
import type { LayaRecord } from "@/lib/types";

export function EvaluationDots({ records }: { records: LayaRecord[] }) {
  const evaluated = records.filter((record) => record.evaluation);
  if (evaluated.length === 0) return null;

  const correct = evaluated.filter(
    (record) => record.evaluation?.correct,
  ).length;
  const wrong = evaluated.length - correct;
  const methodsLabel = `${evaluated.length} ${
    evaluated.length === 1 ? "método avaliado" : "métodos avaliados"
  }`;
  const countsLabel = `${correct} ${
    correct === 1 ? "acerto" : "acertos"
  } e ${wrong} ${wrong === 1 ? "erro" : "erros"}`;

  return (
    <span
      className="inline-flex flex-wrap items-center gap-1"
      aria-label={`${methodsLabel}: ${countsLabel}`}
      title={`${countsLabel} entre ${methodsLabel}`}
    >
      {evaluated.map((record, index) => {
        const evaluation = record.evaluation;
        if (!evaluation) return null;
        const method =
          record.methodSignature || record.method || record.className || "—";
        return (
          <span
            key={`${record.className}-${method}-${index}`}
            className={`h-3 w-3 rounded-full ${
              evaluation.correct ? "bg-green-500" : "bg-red-500"
            }`}
            title={`${method}: ${
              evaluation.correct ? "acertou" : "errou"
            } — esperado: ${groundTruthLabel(
              evaluation.expected,
            )}; previsto: ${groundTruthLabel(evaluation.predicted)}`}
          />
        );
      })}
    </span>
  );
}
