import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { DashboardPage } from './pages/DashboardPage'
import { StationPage } from './pages/StationPage'
import { ReportPage } from './pages/ReportPage'
import { ReplayPage } from './pages/ReplayPage'
import { BenchmarkPage } from './pages/BenchmarkPage'

const router = createBrowserRouter([
  { path: '/', element: <DashboardPage /> },
  { path: '/station/:id', element: <StationPage /> },
  { path: '/report/:id', element: <ReportPage /> },
  { path: '/replay', element: <ReplayPage /> },
  { path: '/benchmark', element: <BenchmarkPage /> },
])

export default function App() {
  return <RouterProvider router={router} />
}
