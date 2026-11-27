import {type RouteConfig, index, route} from '@react-router/dev/routes';

/** The site's pages: the lobby, one table page per game, and sign-in. */
export const routes = [
  index('routes/table.tsx', {id: 'lobby'}),
  route('game/:name', 'routes/table.tsx', {id: 'game'}),
  route('auth/:path', 'routes/auth.tsx', {id: 'auth'}),
] satisfies RouteConfig;

export default routes;
