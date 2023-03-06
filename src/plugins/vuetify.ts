import '@mdi/font/css/materialdesignicons.css'
import {createVuetify} from 'vuetify'
import {VDataTable, VDataTableVirtual} from 'vuetify/labs/VDataTable'

export default createVuetify({
  components: {
    VDataTable,
    VDataTableVirtual
  },
  theme: {
    themes: {
      light: {
        colors: {
          primary: '#007bff',
          secondary: '#eee',
        },
      },
    },
  },
})
