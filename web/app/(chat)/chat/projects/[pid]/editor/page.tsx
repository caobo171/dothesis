import { ThesisEditor } from "../../../../../components/editor/ThesisEditor";

export default async function EditorPage({ params }: { params: Promise<{ pid: string }> }) {
  const { pid } = await params;
  return <ThesisEditor projectId={pid} />;
}
