import { ProfileShell } from "@/components/ProfileShell";
import { OAuthBindings } from "@/components/profile/OAuthBindings";

export default function OAuthPage() {
  return (
    <ProfileShell
      title="关联账号"
      subtitle="将微信、QQ、GitHub 关联至通行证，实现跨平台一键登录。"
    >
      <OAuthBindings />
    </ProfileShell>
  );
}
