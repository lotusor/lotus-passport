import { ProfileShell } from "@/components/ProfileShell";
import { BasicProfile } from "@/components/profile/BasicProfile";

export default function BasicPage() {
  return (
    <ProfileShell
      title="个人资料"
      subtitle="管理你的昵称、头像与联系方式。资料越完整，账户体验越顺畅。"
    >
      <BasicProfile />
    </ProfileShell>
  );
}
