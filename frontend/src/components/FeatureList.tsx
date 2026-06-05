import { BookOpen, ExternalLink } from "lucide-react";
import type { FeaturePoint } from "../api/types";

type Props = {
  features: FeaturePoint[];
  selectedFeatureId?: string;
  onSelect: (id: string) => void;
};

export function FeatureList({ features, selectedFeatureId, onSelect }: Props) {
  return (
    <section className="panel feature-panel">
      <div className="panel-heading">
        <div>
          <h2>功能点</h2>
          <p>从用户手册 RAG 抽取，保留证据引用</p>
        </div>
        <BookOpen size={20} />
      </div>
      <div className="feature-list">
        {features.map((feature) => (
          <button
            className={`feature-row ${selectedFeatureId === feature.id ? "active" : ""}`}
            key={feature.id}
            onClick={() => onSelect(feature.id)}
          >
            <span className={`priority ${feature.priority}`}>{feature.priority}</span>
            <span className="feature-name">{feature.name}</span>
            <span className="feature-desc">{feature.description}</span>
            <span className="refs">
              {feature.doc_refs.slice(0, 2).map((ref) => (
                <a href={ref.url} target="_blank" rel="noreferrer" key={ref.id}>
                  <ExternalLink size={13} />
                  {ref.title}
                </a>
              ))}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
