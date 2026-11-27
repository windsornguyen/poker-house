import type {Config} from '@react-router/dev/config';

export default {
  appDirectory: 'src',
  buildDirectory: 'dist',
  ssr: false,
  prerender: ['/', '/game/poker_house', '/game/poker_house_acpc'],
} satisfies Config;
