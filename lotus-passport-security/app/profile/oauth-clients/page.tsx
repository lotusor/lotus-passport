import { ProfileShell } from "@/components/ProfileShell";
import { OAuthClients } from "@/components/profile/OAuthClients";

export default function OAuthClientsPage() {
  return (
    <ProfileShell
      title="授权应用"
      subtitle="管理接入通行证的应用（OAuth 客户端）：签发统一 JWT，供 E-algo Rank 等系统验证用户身份。"
    >
      <OAuthClients />
    </ProfileShell>
  );
}
