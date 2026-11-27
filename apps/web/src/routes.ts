import {type RouteConfig, index, route} from '@react-router/dev/routes';

/** The site's pages: the lobby, one table page per game, sign-in, and chips for admins. */
export const routes = [
  index('routes/table.tsx', {id: 'lobby'}),
  route('game/:name', 'routes/table.tsx', {id: 'game'}),
  route('auth/:path', 'routes/auth.tsx', {id: 'auth'}),
  route('admin', 'routes/admin.tsx', {id: 'admin'}),
] satisfies RouteConfig;

export default routes;
