import {type RouteConfig, index, route} from '@react-router/dev/routes';

/** The site's pages: the lobby, and one table page per game. */
export const routes = [
  index('routes/table.tsx', {id: 'lobby'}),
  route('game/:name', 'routes/table.tsx', {id: 'game'}),
] satisfies RouteConfig;

export default routes;
