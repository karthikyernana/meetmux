import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createBrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import { AppShell } from "@/app/AppShell";
import { WorkspacesPage } from "@/features/workspaces/WorkspacesPage";
import { WorkspaceOverviewPage } from "@/features/workspaces/WorkspaceOverviewPage";
import { WorkloadPage } from "@/features/workload/WorkloadPage";
import { QueryDetailPage } from "@/features/queries/QueryDetailPage";
import { ExperimentPage } from "@/features/experiments/ExperimentPage";
import { RecommendationsPage } from "@/features/recommendations/RecommendationsPage";
import { RecommendationDetailPage } from "@/features/recommendations/RecommendationDetailPage";
import { IndexInventoryPage } from "@/features/indexes/IndexInventoryPage";
import { HistoryPage } from "@/features/workspaces/HistoryPage";
import { SettingsPage } from "@/features/settings/SettingsPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <WorkspacesPage /> },
      { path: "workspaces", element: <WorkspacesPage /> },
      { path: "workspaces/:workspaceId", element: <WorkspaceOverviewPage /> },
      { path: "workspaces/:workspaceId/workload", element: <WorkloadPage /> },
      { path: "workspaces/:workspaceId/queries/:queryId", element: <QueryDetailPage /> },
      {
        path: "workspaces/:workspaceId/queries/:queryId/experiments/:experimentId",
        element: <ExperimentPage />,
      },
      { path: "workspaces/:workspaceId/recommendations", element: <RecommendationsPage /> },
      {
        path: "workspaces/:workspaceId/recommendations/:recommendationId",
        element: <RecommendationDetailPage />,
      },
      { path: "workspaces/:workspaceId/indexes", element: <IndexInventoryPage /> },
      { path: "workspaces/:workspaceId/history", element: <HistoryPage /> },
      { path: "workspaces/:workspaceId/settings", element: <SettingsPage /> },
    ],
  },
]);

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <Toaster
        position="bottom-right"
        theme="dark"
        toastOptions={{
          style: {
            background: "hsl(222, 47%, 10%)",
            border: "1px solid hsl(217, 33%, 18%)",
            color: "hsl(210, 40%, 98%)",
          },
        }}
      />
    </QueryClientProvider>
  );
}
