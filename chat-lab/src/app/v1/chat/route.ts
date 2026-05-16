import { POST as handlePost } from "@/app/api/v1/chat/route";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const POST = handlePost;
