import { createBrowserRouter, Navigate } from 'react-router-dom';
import AppFrame from './shell/AppFrame';
import ShellGuard from './shell/ShellGuard';
import ShellLayout from './shell/ShellLayout';
import Investments from './shell/screens/Investments';
import Overview from './shell/screens/Overview';
import Placeholder from './shell/screens/Placeholder';
import StartDepot from './shell/screens/StartDepot';
import Welcome from './shell/screens/Welcome';
import QuestLayout from './quest/QuestLayout';
import WhatAreYouInto from './quest/screens/WhatAreYouInto';

export const routes = [
  {
    element: <AppFrame />,
    children: [
      { path: '/', element: <Welcome /> },
      {
        element: (
          <ShellGuard>
            <ShellLayout />
          </ShellGuard>
        ),
        children: [
          { path: '/overview', element: <Overview /> },
          { path: '/investments', element: <Investments />, handle: { title: 'Investments' } },
          {
            path: '/investments/startdepot',
            element: <StartDepot />,
            handle: { title: 'StartDepot', back: true },
          },
          { path: '/payments', element: <Placeholder />, handle: { title: 'Payments' } },
          { path: '/service', element: <Placeholder />, handle: { title: 'Service' } },
          { path: '/profile', element: <Placeholder />, handle: { title: 'Profile' } },
        ],
      },
      {
        path: '/quest',
        element: (
          <ShellGuard>
            <QuestLayout />
          </ShellGuard>
        ),
        children: [{ index: true, element: <WhatAreYouInto /> }],
      },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
