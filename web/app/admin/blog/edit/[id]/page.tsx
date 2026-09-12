import { PostEditor } from "../../_components/PostEditor";

/** `params` is a promise in Next 15 — awaited here so the editor stays a plain
 *  client component that takes an id. */
export default async function EditPostPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <PostEditor postId={id} />;
}
