import type { RelationTree } from "./graph";

interface Props {
  tree: RelationTree;
}

export function RelationTreeView({ tree }: Props) {
  return (
    <div className="relation-tree" aria-label="Relationer">
      <div className="relation-root">{tree.root.label}</div>
      <ul className="relation-branches">
        {tree.children.map((child, i) => (
          <li key={child.id ?? `syn-${i}`} className="relation-branch">
            <span className="relation-line" aria-hidden />
            <div className="relation-node">
              <span className="relation-name">{child.label}</span>
              {child.relation_label && (
                <span className="relation-meta">
                  {child.relation_label}
                  {child.source ? ` · ${child.source}` : ""}
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
