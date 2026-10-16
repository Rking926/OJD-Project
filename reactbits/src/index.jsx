// Point d'entrée du bundle : expose les composants React Bits à l'UI vanilla
// (frontend/app.js) via window.ReactBits. PromptBar, VoicePill, LatticeLoader,
// SwipeRow et SwipeToast sont copiés tels quels depuis le registre React Bits
// (variante JS-CSS) ; ConversationList (SwipeRow) et Toaster (SwipeToast) sont
// propres à OJD.
import { createRoot } from 'react-dom/client';
import {
  Brain02Icon,
  Call02Icon,
  Database01Icon,
  GithubIcon,
  Globe02Icon,
  InstagramIcon,
  Location01Icon,
  Mail01Icon,
  Search01Icon,
  ServerStack01Icon,
  Shield01Icon,
  UserSearch01Icon,
  Wrench01Icon
} from '@hugeicons/core-free-icons';

import PromptBar from './PromptBar';
import VoicePill from './VoicePill';
import LatticeLoader from './LatticeLoader';
import SwipeRow from './SwipeRow';
import ConversationList from './ConversationList';
import { toast } from './Toaster';

const COMPONENTS = { PromptBar, VoicePill, LatticeLoader, SwipeRow, ConversationList };

// Icônes utilisables par nom depuis le JS vanilla (ex: sources de PromptBar).
const ICONS = {
  brain: Brain02Icon,
  phone: Call02Icon,
  database: Database01Icon,
  github: GithubIcon,
  globe: Globe02Icon,
  instagram: InstagramIcon,
  location: Location01Icon,
  mail: Mail01Icon,
  search: Search01Icon,
  server: ServerStack01Icon,
  shield: Shield01Icon,
  user: UserSearch01Icon,
  tool: Wrench01Icon
};

const resolve = props => {
  if (!Array.isArray(props.sources)) return props;
  return {
    ...props,
    sources: props.sources.map(s => (typeof s.icon === 'string' ? { ...s, icon: ICONS[s.icon] || Wrench01Icon } : s))
  };
};

// Monte un composant dans `el`. Renvoie { update(props), unmount() } ;
// update() fusionne les nouvelles props avec les précédentes.
const mount = (name, el, props = {}) => {
  const Component = COMPONENTS[name];
  if (!Component) throw new Error(`Composant React Bits inconnu : ${name}`);
  const root = createRoot(el);
  let current = props;
  const render = () => root.render(<Component {...resolve(current)} />);
  render();
  return {
    update(next) {
      current = { ...current, ...next };
      render();
    },
    unmount() {
      root.unmount();
    }
  };
};

window.ReactBits = { mount, toast, icons: Object.keys(ICONS) };
