import { Activity, CheckCircle2, Loader2, XCircle } from "lucide-react";
import type { ExecutionRun } from "../api/types";

type Props = {
  runs: ExecutionRun[];
};

export function RunTimeline({ runs }: Props) {
  const latest = runs[0];
  const statusIcon =
    latest?.status === "running" || latest?.status === "pending" ? (
      <Loader2 className="spin" size={20} />
    ) : latest?.status === "passed" ? (
      <CheckCircle2 size={20} />
    ) : (
      <XCircle size={20} />
    );
  return (
    <section className="panel timeline-panel">
      <div className="panel-heading">
        <div>
          <h2>执行轨迹</h2>
          <p>规划、动作、观察、验证结论</p>
        </div>
        <Activity size={20} />
      </div>
      {!latest ? (
        <div className="empty">尚未执行测试场景</div>
      ) : (
        <div className="run-detail">
          <div className="run-summary">
            {statusIcon}
            <strong>{latest.id}</strong>
            <span className={latest.status}>{latest.status}</span>
            <span>{latest.metrics.duration_seconds ?? 0}s</span>
            <span>score {latest.verdict?.score ?? "-"}</span>
          </div>
          <div className="verdict">
            {latest.failure_reason || latest.verdict?.failure_reason || "验证器未发现阻断性失败"}
          </div>
          {latest.trace.length ? (
            <div className="trace-list">
              {latest.trace.slice(-6).map((item, index) => (
                <span key={`${item}-${index}`}>{item}</span>
              ))}
            </div>
          ) : null}
          <div className="timeline">
            {latest.actions.map((action) => (
              <div className={`timeline-row ${action.status}`} key={action.index}>
                <span className="index">{action.index}</span>
                <div>
                  <strong>{action.tool}</strong>
                  <p>{action.thought}</p>
                  {action.observation ? <small>{action.observation}</small> : null}
                  {action.error ? <em>{action.error}</em> : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
