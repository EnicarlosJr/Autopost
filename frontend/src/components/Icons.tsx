import {SvgIcon, type SvgIconProps} from '@mui/material';

// Conjunto pequeno de ícones (desenhos do Material Symbols) para não carregar uma biblioteca inteira.
const make = (path: string) => (props: SvgIconProps) => <SvgIcon {...props}><path d={path}/></SvgIcon>;

export const PauseIcon = make('M6 19h4V5H6v14zm8-14v14h4V5h-4z');
export const PlayIcon = make('M8 5v14l11-7z');
export const StopIcon = make('M6 6h12v12H6z');
export const CopyIcon = make('M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z');
export const DeleteIcon = make('M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z');
export const EditIcon = make('M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z');
export const ExpandIcon = make('M16.59 8.59 12 13.17 7.41 8.59 6 10l6 6 6-6z');
export const RefreshIcon = make('M17.65 6.35A7.96 7.96 0 0 0 12 4a8 8 0 1 0 7.73 10h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z');
export const SearchIcon = make('M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z');
export const FilterIcon = make('M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z');
export const CloseIcon = make('M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z');
export const AddIcon = make('M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z');
export const SendIcon = make('M2.01 21 23 12 2.01 3 2 10l15 2-15 2z');
export const TagIcon = make('M21.41 11.58l-9-9A2 2 0 0 0 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58.55 0 1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41 0-.55-.23-1.06-.59-1.42zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7z');
export const UnfoldMoreIcon = make('M12 5.83 15.17 9l1.41-1.41L12 3 7.41 7.59 8.83 9 12 5.83zm0 12.34L8.83 15l-1.41 1.41L12 21l4.59-4.59L15.17 15 12 18.17z');
export const UnfoldLessIcon = make('M7.41 18.59 8.83 20 12 16.83 15.17 20l1.41-1.41L12 14l-4.59 4.59zm9.18-13.18L15.17 4 12 7.17 8.83 4 7.41 5.41 12 10l4.59-4.59z');
