import { QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { queryClient } from './api/queryClient';
import AppFrame from './shell/AppFrame';
import ShellGuard from './shell/ShellGuard';
import ShellLayout from './shell/ShellLayout';
import Investments from './shell/screens/Investments';
import Overview from './shell/screens/Overview';
import Placeholder from './shell/screens/Placeholder';
import StartDepot from './shell/screens/StartDepot';
import Welcome from './shell/screens/Welcome';
import QuestLayout from './quest/QuestLayout';
import { VoiceProvider } from './voice';
import PhaseGuard from './quest/PhaseGuard';
import QuestEntry from './quest/QuestEntry';
import HeroCreate from './quest/screens/HeroCreate';
import Commit from './quest/screens/Commit';
import Debrief from './quest/screens/Debrief';
import HeroScreen from './quest/screens/HeroScreen';
import Outcome from './quest/screens/Outcome';
import Reflect from './quest/screens/Reflect';
import Xp from './quest/screens/Xp';
import PlayScreen from './quest/play/PlayScreen';
import QuestPlaceholder from './quest/screens/QuestPlaceholder';
import RevealRoute from './quest/screens/RevealRoute';
import QuestBoard from './quest/board/QuestBoard';
import QuestDisclosure from './quest/screens/QuestDisclosure';
import { HERO_CLASS_PATH } from './quest/setupNavigation';

// Screens whose task has not landed yet render a titled placeholder under the phase guard.
const phaseScreens = [
  {
    path: 'play',
    element: (
      <PhaseGuard screen="/quest/play">
        <PlayScreen />
      </PhaseGuard>
    ),
  },
];

export const routes = [
  {
    element: <AppFrame />,
    children: [
      { path: '/', element: <Welcome /> },
      {
        element: (
          <ShellGuard>
            <QueryClientProvider client={queryClient}>
              <ShellLayout />
            </QueryClientProvider>
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
            <QueryClientProvider client={queryClient}>
              <VoiceProvider>
                <QuestLayout />
              </VoiceProvider>
            </QueryClientProvider>
          </ShellGuard>
        ),
        children: [
          { index: true, element: <QuestEntry /> },
          {
            path: 'hero/new',
            element: (
              <PhaseGuard screen="hero-new">
                <HeroCreate />
              </PhaseGuard>
            ),
          },
          {
            path: HERO_CLASS_PATH,
            element: (
              <PhaseGuard screen={HERO_CLASS_PATH}>
                <HeroCreate chooseClass />
              </PhaseGuard>
            ),
          },
          {
            path: 'board',
            element: (
              <PhaseGuard screen="/quest/board">
                <QuestBoard />
              </PhaseGuard>
            ),
          },
          {
            path: 'disclosure',
            element: (
              <PhaseGuard screen="/quest/disclosure">
                <QuestDisclosure />
              </PhaseGuard>
            ),
          },
          ...phaseScreens,
          ...[
            ['commit', <Commit key="c" />],
            ['outcome', <Outcome key="o" />],
            ['debrief', <Debrief key="d" />],
            ['reflect', <Reflect key="r" />],
            ['xp', <Xp key="x" />],
          ].map(([path, el]) => ({
            path: path as string,
            element: <PhaseGuard screen={`/quest/${path as string}`}>{el as React.ReactNode}</PhaseGuard>,
          })),
          {
            path: 'reveal',
            element: (
              <PhaseGuard screen="/quest/reveal">
                <RevealRoute />
              </PhaseGuard>
            ),
          },
          { path: 'hero', element: <HeroScreen /> },
          { path: 'journal/:campaignId?', element: <QuestPlaceholder title="Journal" /> },
        ],
      },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
