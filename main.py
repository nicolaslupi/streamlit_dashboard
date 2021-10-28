import streamlit as st
from streamlit import caching
import utils
import datetime as dt
import pandas as pd

st.set_page_config(page_title="Epic Dashboard", layout='wide', page_icon='🛰') 

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

pagina = st.sidebar.radio('', options=['Caja','Gastos','Aportes'], index=0)
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
  
if pagina == 'Caja':
  st.title("Resumen de Cuentas")
  st.subheader('Estado de Caja')
  utils.caja(data_aux, flow, stock, moneda.lower())
elif pagina == 'Gastos':
  st.title('Reporte de Gastos')
  date_range = st.sidebar.date_input('Rango de fechas', min_value=months[0], value=(dt.date(year=2021, month=1, day=1), data_aux.fecha.iloc[-1]), max_value=data_aux.fecha.values[-1])
  utils.gastos(data_aux, flow, moneda.lower(), date_range)
else:
  st.title('Aportes')
  date_range = st.sidebar.date_input('Rango de fechas', min_value=months[0], value=(months[0], data_aux.fecha.iloc[-1]), max_value=data_aux.fecha.values[-1])
  utils.aportes(data_aux, moneda.lower(), date_range)