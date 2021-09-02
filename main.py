import streamlit as st
from streamlit import caching
import utils
import datetime as dt
import pandas as pd

st.set_page_config(page_title="Epic Dashboard") 

data, data_distr, months, quarters, cuentas = utils.load_data()
data['fecha'] = data.fecha.apply(lambda fecha: dt.datetime.date(pd.to_datetime(fecha)))
data_distr['fecha'] = data_distr.fecha.apply(lambda fecha: dt.datetime.date(pd.to_datetime(fecha)))
months = [dt.datetime.date(month) for month in months]

refresh = st.sidebar.button('Actualizar Datos', help='Elimina Caché y actualiza datos desde Drive')
if refresh:
  caching.clear_cache()
  data, data_distr, months, quarters, cuentas = utils.load_data()
  data['fecha'] = data.fecha.apply(lambda fecha: dt.datetime.date(pd.to_datetime(fecha)))
  data_distr['fecha'] = data_distr.fecha.apply(lambda fecha: dt.datetime.date(pd.to_datetime(fecha)))
  months = [dt.datetime.date(month) for month in months]



st.sidebar.header("Navegación")

pagina = st.sidebar.radio('Reporte', options=['Principal','Gastos'], index=0)
st.sidebar.subheader("Parámetros generales")

moneda = st.sidebar.selectbox(
  'Moneda',
  ['USD','ARS']
)

sites = list(set(data.site))
sites = st.sidebar.multiselect(
  'Empresa',
  sites,
  sites
)

devengado = st.sidebar.checkbox(label='Devengado', help='Distribuye gastos en el tiempo cuando corresponde. Por ejemplo, el caso de un depósito por un alquiler. No son números reales.')

if devengado:
  data_aux, flow, stock = utils.filter(data_distr, sites, moneda.lower())
else:
  data_aux, flow, stock = utils.filter(data, sites, moneda.lower())
  
if pagina == 'Principal':
  st.title("Resumen de Cuentas")
  st.subheader('Estado de Caja')
  utils.caja(data_aux, flow, stock, moneda.lower())
else:
  st.title('Reporte de Gastos')
  utils.gastos(data_aux, flow, moneda.lower(), months)