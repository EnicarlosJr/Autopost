import {alpha, createTheme} from '@mui/material';
import '@fontsource-variable/bricolage-grotesque';
import '@fontsource-variable/albert-sans';

/** Tokens do Autopost: bancada de garimpo de ofertas. O amarelo é só das etiquetas de desconto. */
export const tokens = {
  ink: '#1A2140',        // menu, títulos e ação principal
  inkSoft: '#2B3560',
  paper: '#EDF0F3',      // fundo de trabalho
  surface: '#FFFFFF',
  line: '#DCE1E7',
  muted: '#5B6478',
  sticker: '#FFCB2E',    // etiqueta de desconto
  saving: '#0B8A5A',     // economia, sucesso
  danger: '#D2433B',
  scheduled: '#4B5BDC',
};

export const display = '"Bricolage Grotesque Variable", "Albert Sans Variable", system-ui, sans-serif';
const body = '"Albert Sans Variable", system-ui, -apple-system, "Segoe UI", sans-serif';

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {main: tokens.ink, light: tokens.inkSoft, contrastText: '#fff'},
    secondary: {main: tokens.scheduled},
    success: {main: tokens.saving},
    error: {main: tokens.danger},
    warning: {main: '#B86E00'},
    info: {main: tokens.scheduled},
    background: {default: tokens.paper, paper: tokens.surface},
    text: {primary: tokens.ink, secondary: tokens.muted},
    divider: tokens.line,
  },
  shape: {borderRadius: 10},
  typography: {
    fontFamily: body,
    fontSize: 14,
    h1: {fontFamily: display, fontWeight: 700, letterSpacing: '-0.02em'},
    h2: {fontFamily: display, fontWeight: 700, letterSpacing: '-0.02em'},
    h3: {fontFamily: display, fontWeight: 700, letterSpacing: '-0.02em'},
    h4: {fontFamily: display, fontWeight: 700, fontSize: '2rem', lineHeight: 1.15, letterSpacing: '-0.02em'},
    h5: {fontFamily: display, fontWeight: 650, fontSize: '1.35rem', letterSpacing: '-0.01em'},
    h6: {fontFamily: display, fontWeight: 650, fontSize: '1.1rem'},
    subtitle1: {fontWeight: 600},
    body1: {lineHeight: 1.55},
    body2: {lineHeight: 1.5},
    button: {textTransform: 'none', fontWeight: 600, letterSpacing: 0},
    caption: {color: tokens.muted},
  },
  components: {
    MuiCssBaseline: {styleOverrides: {
      body: {fontFeatureSettings: '"tnum" 1', WebkitFontSmoothing: 'antialiased'},
      '::selection': {background: alpha(tokens.sticker, .6)},
      a: {color: tokens.ink, textDecorationColor: alpha(tokens.ink, .35), textUnderlineOffset: 3},
      'a:hover': {textDecorationColor: tokens.ink},
      ':focus-visible': {outline: `2px solid ${tokens.scheduled}`, outlineOffset: 2},
      '@media (prefers-reduced-motion: reduce)': {'*': {transition: 'none !important', animation: 'none !important'}},
    }},
    MuiButton: {
      defaultProps: {disableElevation: true},
      styleOverrides: {
        root: {borderRadius: 9, paddingInline: 14},
        sizeSmall: {paddingInline: 10},
        outlined: {borderColor: tokens.line, '&:hover': {borderColor: tokens.ink, background: alpha(tokens.ink, .03)}},
      },
    },
    MuiCard: {
      defaultProps: {elevation: 0},
      styleOverrides: {root: {border: `1px solid ${tokens.line}`, borderRadius: 14}},
    },
    MuiPaper: {styleOverrides: {rounded: {borderRadius: 14}}},
    MuiDialog: {styleOverrides: {paper: {borderRadius: 18, border: 'none'}}},
    MuiDialogTitle: {styleOverrides: {root: {fontFamily: display, fontWeight: 700, fontSize: '1.35rem', paddingTop: 22}}},
    MuiChip: {
      styleOverrides: {
        root: {borderRadius: 7, fontWeight: 600},
        sizeSmall: {height: 24, fontSize: 12.5},
        outlined: {borderColor: tokens.line},
      },
    },
    MuiTabs: {styleOverrides: {indicator: {height: 3, borderRadius: 3, backgroundColor: tokens.ink}}},
    MuiTab: {styleOverrides: {root: {textTransform: 'none', fontWeight: 600, fontSize: 14.5, minHeight: 46, paddingInline: 14,
      color: tokens.muted, '&.Mui-selected': {color: tokens.ink}}}},
    MuiOutlinedInput: {styleOverrides: {
      root: {background: tokens.surface, '& .MuiOutlinedInput-notchedOutline': {borderColor: tokens.line}},
    }},
    MuiAlert: {styleOverrides: {root: {borderRadius: 12, alignItems: 'center'}, standardInfo: {background: alpha(tokens.scheduled, .08)}}},
    MuiTooltip: {styleOverrides: {tooltip: {background: tokens.ink, fontSize: 12.5}}},
    MuiLinearProgress: {styleOverrides: {root: {borderRadius: 4, height: 3}}},
    MuiLink: {styleOverrides: {root: {fontWeight: 600}}},
    MuiSwitch: {styleOverrides: {switchBase: {'&.Mui-checked': {color: tokens.saving, '& + .MuiSwitch-track': {backgroundColor: tokens.saving}}}}},
  } as any,
});
