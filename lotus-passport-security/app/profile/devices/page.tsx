import { ProfileShell } from "@/components/ProfileShell";
import { DevicesView } from "@/components/profile/DevicesView";

export default function DevicesPage() {
  return (
    <ProfileShell
      title="登录设备"
      subtitle="查看并管理已授权登录的设备，以及近期的登录活动记录。"
    >
      <DevicesView />
    </ProfileShell>
  );
}
