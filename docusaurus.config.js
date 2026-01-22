// @ts-check

const { themes } = require('prism-react-renderer');

const lightCodeTheme = themes.github;
const darkCodeTheme = themes.dracula;

const organizationName = 'its-DeFine';
const projectName = 'livepeer-delegation-research';
const isGitHubPages = process.env.DEPLOY_TARGET === 'github-pages';

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'Livepeer Delegation Research',
  tagline:
    'Evidence-based research on Livepeer delegation on Arbitrum: acquisition, retention, cashout behavior, and solution evaluation.',
  url: isGitHubPages
    ? 'https://its-define.github.io'
    : 'https://livepeer-delegation-research.vercel.app',
  baseUrl: isGitHubPages ? `/${projectName}/` : '/',
  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'warn',
  favicon: 'img/favicon.svg',
  organizationName,
  projectName,
  trailingSlash: false,

  presets: [
    [
      'classic',
      {
        docs: {
          path: 'docs',
          routeBasePath: 'docs',
          sidebarPath: require.resolve('./sidebarsDocs.js')
        },
        blog: false,
        theme: {
          customCss: require.resolve('./src/css/custom.css')
        }
      }
    ]
  ],

  plugins: [
    [
      '@docusaurus/plugin-content-docs',
      {
        id: 'solutions',
        path: 'solutions',
        routeBasePath: 'solutions',
        sidebarPath: require.resolve('./sidebarsSolutions.js'),
        exclude: ['**/README.md', '**/_template.md']
      }
    ],
    [
      '@docusaurus/plugin-content-docs',
      {
        id: 'research',
        path: 'research',
        routeBasePath: 'research',
        sidebarPath: require.resolve('./sidebarsResearch.js'),
        exclude: ['**/README.md']
      }
    ]
  ],

  themeConfig: {
    colorMode: {
      defaultMode: 'dark',
      respectPrefersColorScheme: true
    },
    navbar: {
      title: 'Livepeer Delegation Research',
      logo: {
        alt: 'Livepeer Delegation Research',
        src: 'img/logo-light.svg',
        srcDark: 'img/logo-dark.svg'
      },
      items: [
        { to: '/docs/statement', label: 'Statement', position: 'left' },
        { to: '/docs/analytics', label: 'Analytics', position: 'left' },
        { to: '/docs/directions', label: 'Directions', position: 'left' },
        { to: '/solutions', label: 'Solutions', position: 'left' },
        { to: '/research', label: 'Research', position: 'left' },
        {
          href: 'https://github.com/its-DeFine/livepeer-delegation-research',
          label: 'GitHub',
          position: 'right'
        }
      ]
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Start',
          items: [
            { label: 'Statement', to: '/docs/statement' },
            { label: 'Analytics', to: '/docs/analytics' },
            { label: 'Directions', to: '/docs/directions' },
            { label: 'Overview', to: '/docs/overview' },
            { label: 'Rubric', to: '/docs/rubric' },
            { label: 'Scoreboard', to: '/docs/scoreboard' }
          ]
        },
        {
          title: 'Solutions',
          items: [
            { label: 'Lisar', to: '/solutions/lisar' },
            { label: 'IDOL / Arrakis', to: '/solutions/ydol' },
            { label: 'Tenderize', to: '/solutions/tenderize' }
          ]
        },
        {
          title: 'Research',
          items: [
            { label: 'Notes index', to: '/research' },
            { label: 'Delegation board', to: '/research/delegation-board' },
            {
              label: 'Outflows',
              to: '/research/livepeer-delegator-outflows-research'
            },
            {
              label: 'Incentives',
              to: '/research/livepeer-delegator-incentives'
            }
          ]
        }
      ],
      copyright: `© ${new Date().getFullYear()} Livepeer Delegation Research`
    },
    prism: {
      theme: lightCodeTheme,
      darkTheme: darkCodeTheme
    }
  }
};

module.exports = config;
