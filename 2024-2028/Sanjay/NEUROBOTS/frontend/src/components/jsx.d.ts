declare module "@/components/*.jsx";
declare module "@/components/TriageDashboard" {
  import type { ComponentType } from "react";

  const TriageDashboard: ComponentType<{
    staffUser: import("@/lib/api").StaffUser;
    onLogout: () => void;
  }>;
  export default TriageDashboard;
}
