import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from 'i18next-browser-languagedetector';
import moment from 'moment';

// the translations
import 'moment/locale/fr'
import fr from './labels.fr.json';
import en from './labels.en.json';
const resources = {fr, en};

function formatterValeur(value, format, lng) {
  if(value instanceof Date) {
    return moment(value).locale(lng).format(format);
  } else if(!isNaN(value) && !isNaN(format)) {
    return Number(value).toFixed(format);
  }

  return value;
}

i18n
  .use(LanguageDetector)
  .use(initReactI18next) // passes i18n down to react-i18next
  .init({
    resources,
    fallbackLng: 'fr',

    keySeparator: '.', // we use keys in form messages.welcome

    interpolation: {
      escapeValue: false, // react is already safe from xss,
      format: formatterValeur
    }
  });

export default i18n;
