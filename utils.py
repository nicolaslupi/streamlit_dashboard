import os
import wget
import streamlit as st
import streamlit.components.v1 as components
from st_aggrid import AgGrid
from st_aggrid.grid_options_builder import GridOptionsBuilder
import pandas as pd
import numpy as np
import datetime as dt
from dateutil.relativedelta import relativedelta
import re
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from pivottablejs import pivot_ui

Caja = set(['caja ars','caja usd','ml','banco','electronica','estructuras','propulsion','accounting','sendwyre'])
Transferencias = set(['epic'])
Aportes = set(['aportes','montero'])
Deudas = set(['cuentas a pagar'])
OPEX = set(['transporte','consumibles generales','consumibles de oficina','consumibles de ensayos',
            'consumibles para produccion de propelente',])
Otros_gastos = set(['impuestos','legal','variacion de inventario','otros gastos varios','perdida por tc','perdida por arqueo'])
Otros_ingresos = set(['ganancia por tc','ganancia por arqueo','otros ingresos varios'])
FOPEX = set(['sg&a salaries','tech salaries','suscripciones','alquiler'])
CAPEX = set(['herramientas','materiales','infraestructura','mano de obra','rodados','equipo de oficina'])
general_rd = set(['propulsion r&d','electronics r&d'])
Hardware = set(['test equipment','vehicle r&d','propellant production hardware']).union(general_rd)

cuentas_gastos = OPEX.union(Otros_gastos, FOPEX, CAPEX, Hardware)
activo = Caja.union(OPEX, Otros_gastos, FOPEX, CAPEX, Hardware, Transferencias)
pasivo = Aportes.union(Deudas, Otros_ingresos)

def normalize(s):
    replacements = (
        ('á','a'),
        ('é','e'),
        ('í','i'),
        ('ó','o'),
        ('ú','u')
    )

    for a, b in replacements:
        s = s.replace(a, b).replace(a.upper(), b.upper())
    return s

def process_string(s):
    if pd.isna(s):
        return s
    else:
        return normalize( re.sub(' +', ' ', str(s).lower()) )

def distribute_over_months(data):
    over_months = data[~pd.isna(data.over_months)]
    rows = []
    for idx, row in over_months.iterrows():
        months = row.over_months
        monto = row.usd / months
        row.over_months = np.nan
        row.usd = monto
        data.loc[idx] = row
        for _ in np.arange(1, months):
            row.month = row.month + relativedelta(months=+1)
            row.fecha = row.fecha + relativedelta(months=+1)
            rows.append( row.copy() )
            
    data = data.append( rows )    
    data.reset_index(drop=True, inplace=True) 
    data.drop(data[data.fecha >= dt.datetime.today()].index, inplace=True)
    
    return data.sort_values(by=['fecha','id']).reset_index(drop=True)

def get(data, cuenta, moneda):
    if cuenta in activo:
        res = data[data.destino == cuenta][moneda].sum() - data[data.origen == cuenta][moneda].sum()
    elif cuenta in pasivo:
        res = data[data.origen == cuenta][moneda].sum() - data[data.destino == cuenta][moneda].sum()
    return res

class Proyectos():
  def __init__(self, data):
    self.flow = pd.DataFrame(index=pd.unique(data.month))
    self.proyectos = set(data.proyecto)
    sumas = pd.pivot_table( data, values='usd', index='month', columns=['proyecto','destino'], aggfunc=sum, fill_value=0)
    restas = pd.pivot_table( data, values='usd', index='month', columns=['proyecto','origen'], aggfunc=sum, fill_value=0)
    restas.columns.names = ['proyecto','destino']
    tmp = sumas.sub(restas, axis=1, fill_value=0)
    
    self.flow[list(self.proyectos)] = np.array([tmp[proyecto][set(tmp[proyecto].columns)&cuentas_gastos].sum(axis=1) for proyecto in self.proyectos]).transpose()
    self.stock = self.flow.cumsum()  

@st.cache(allow_output_mutation=True)
def load_data():
    filename = 'data.xlsx'
    if os.path.exists(filename):
        os.remove(filename)
    wget.download('https://drive.google.com/uc?export=download&id=1Bji9YatH0J5vEtOzSvCmv23lS92rDPuP', 'data.xlsx')

    data = pd.read_excel('data.xlsx', sheet_name='Input', header=2)
    data['site'] = 'Epic'
    data_us = pd.read_excel('data.xlsx', sheet_name='Input US', header=2)
    data_us['site'] = 'Montero'

    data = data.append(data_us, ignore_index=True).sort_values(['Fecha','Id']).reset_index(drop=True)
    data.columns = [col.lower().replace(' ', '_') for col in data.columns]
    data.drop(['year','month'], axis=1, inplace=True)
    data['month'] = data.fecha.apply(lambda fecha: fecha.replace(day=1))
    data['quarter'] = data.month.apply(lambda fecha: fecha.replace(month=int(np.ceil(fecha.month/3))))
    data['cuenta'] = data.cuenta.apply(process_string)
    data['detalle'] = data.detalle.apply(process_string)
    data['proveedor'] = data.proveedor.apply(process_string)
    data['destino'] = data.destino.apply(process_string)
    data['origen'] = data.origen.apply(process_string)
    months = pd.to_datetime(pd.unique(data.month))
    quarters = pd.unique(data.quarter)
    cuentas = set(data.destino).union(set(data.origen))

    data_distr = distribute_over_months(data.copy())

    return data, data_distr, months, quarters, cuentas

@st.cache
def filter(data, sites, moneda):
    data = data[data.site.isin(sites)].reset_index(drop=True)
    flow = pd.pivot_table( data, values=moneda, index='month', columns='destino', aggfunc=sum, fill_value=0).sub( \
           pd.pivot_table( data, values=moneda, index='month', columns='origen', aggfunc=sum, fill_value=0), \
           axis=1, fill_value=0)

    flow['Caja'] = flow[set(flow.columns)&Caja].sum(axis=1)
    flow['FOPEX'] = flow[set(flow.columns)&FOPEX].sum(axis=1)
    flow['OPEX'] = flow[set(flow.columns)&OPEX].sum(axis=1)
    flow['CAPEX'] = flow[set(flow.columns)&CAPEX].sum(axis=1)
    flow['Hardware'] = flow[set(flow.columns)&Hardware].sum(axis=1)
    flow['Otros_gastos'] = flow[set(flow.columns)&Otros_gastos].sum(axis=1)

    flow['Outflows'] = flow[['FOPEX','OPEX','CAPEX','Hardware','Otros_gastos']].sum(axis=1)
    
    stock = flow.cumsum()
    
    flow['MA'] = flow['Outflows'].rolling(window=3).mean()
    flow.iloc[-1,-1] = flow.iloc[-2,-1]

    return data.copy(), flow, stock

@st.cache
def get_proyectos(data):
    proyectos = Proyectos(data)
    return proyectos

def caja(data, flow, stock, moneda):
    cuenta = st.selectbox(label='Cuenta', options=list(map(str.title, ['Todas']+list(Caja))), index=0).lower()
    
    if cuenta == 'todas':
        cuenta = 'Caja'

    st.write('Saldo actual:', moneda.upper(), '{:,.2f}'.format(stock.tail(1)[cuenta].values[0]))

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=stock.index,
            y=stock[cuenta],
            name='Stock'
        )
    )

    fig.add_trace(
        go.Bar(
            x=flow.index,
            y=flow[cuenta],
            name='Flujo'
        )
    )

    fig.update_yaxes(title_text=moneda.upper())
    fig.update_layout(title='<b>Estado de Caja</b>')
    st.plotly_chart(fig, use_container_width=True)

    
    st.write('Burn actual:', moneda.upper(), '{:,.0f} por mes'.format(flow.tail(1)['MA'].values[0]))
    st.write('Runway: {:,.0f} meses'.format((stock.tail(1)['Caja'] / flow.tail(1)['MA']).values[0]))

    fig = make_subplots( specs = [[{'secondary_y':True}]] )

    fig.add_trace(
        go.Scatter(
            x=flow.index,
            y=flow.MA,
            name='Burn'
        ),
        secondary_y=False
    )

    fig.add_trace(
        go.Scatter(
            x=flow.index,
            y=stock.Caja / flow.MA,
            name='Runway'
        ),
        secondary_y=True
    )

    fig.update_layout(title='<b>Monthly Burn - Trailing 3 Months MA</b>')
    fig.update_yaxes(title_text="US$", secondary_y=False)
    fig.update_yaxes(title_text="Months", secondary_y=True)

    st.plotly_chart(fig, use_container_width=True)

    st.subheader('Últimos movimientos:')

    flujo_nombre = 'flujo (' + moneda + ')'
    stock_nombre = 'stock (' + moneda + ')'
    
    if cuenta == 'Caja':
        mayor = data[(data.destino.isin(Caja)) | (data.origen.isin(Caja))].reset_index(drop=True).copy()
        mayor[flujo_nombre] = mayor[moneda] * ( (mayor.origen.isin(Caja))*-1 + (mayor.destino.isin(Caja))*1 )
        
    else:
        mayor = data[(data.destino == cuenta) | (data.origen == cuenta)].reset_index(drop=True).copy()
        mayor[flujo_nombre] = mayor[moneda] * ( (mayor.origen == cuenta)*-1 + (mayor.destino == cuenta)*1 )

    mayor[stock_nombre] = mayor[flujo_nombre].cumsum()
    mayor = mayor[['id','fecha',flujo_nombre,stock_nombre,'categoria','sub_categoria_1','proyecto','cuenta','proveedor','detalle','comprobante','site']]
    mayor[flujo_nombre] = mayor[flujo_nombre].map('${:,.2f}'.format)
    mayor[stock_nombre] = mayor[stock_nombre].map('${:,.2f}'.format)
    #mayor[flujo] = mayor[flujo].round(2)
    #mayor[stock] = mayor[stock].round(2)
    mayor = mayor[::-1]
    mayor.fillna('', inplace=True)
    
    gb = GridOptionsBuilder.from_dataframe(mayor)
    gb.configure_pagination()
    gb.configure_side_bar()
    gb.configure_default_column(groupable=True, value=True, enableRowGroup=True, aggFunc='sum', editable=True)
    gridOptions = gb.build()
    
    #gridOptions['columnDefs'] = [{'field':col, 'pivot':True, 'value':True} if col in ['categoria','sub_categoria_1'] else \
    #    {'field':col, 'pivot':False, 'value':True} for col in mayor.columns]
    AgGrid(mayor, gridOptions = gridOptions)#, enable_enterprise_modules=True)

def gastos(data, flow, moneda, months):
    fig = go.Figure(data=[
          go.Bar(name='FOPEX', x=flow.index, y=flow.FOPEX),
          go.Bar(name='OPEX', x=flow.index, y=flow.OPEX),
          go.Bar(name='Hardware', x=flow.index, y=flow.Hardware),
          go.Bar(name='CAPEX', x=flow.index, y=flow.CAPEX),
          go.Bar(name='Otros gastos', x=flow.index, y=flow.Otros_gastos),
    ])
    
    fig.add_trace(
        go.Scatter(
            x=flow.index,
            y=flow.MA,
            name='MA'
        )
    )

    fig.update_layout(barmode='stack', title='<b>Gastos Mensuales</b>')#, height=500)
    fig.update_yaxes(title_text=moneda.upper())
    st.plotly_chart(fig, use_container_width=True)

    st.title('Proyectos')
    
    format = 'MM/YY'
    cols1,_ = st.columns((1,2))
    
    with cols1:
        date_range = st.slider('Rango de fechas', min_value=months[0], value=(dt.date(year=2021, month=1, day=1), months[-1]), max_value=months[-1], format=format)
        
    with st.expander('Proyectos'):
        proyectos = ['Todos'] + list(set(data.proyecto))
        proyectos.remove('Global')

        proyectos_elegidos = st.multiselect('', proyectos, ['Todos'])
        if 'Todos' in proyectos_elegidos:
            proyectos_elegidos = proyectos

    data_proyectos = data[
                            (data.fecha.between(date_range[0], date_range[1])) &
                            (data.proyecto.isin(proyectos_elegidos))
                        ].sort_values(['fecha','id']).reset_index(drop=True).copy()
    
    proyectos = get_proyectos(data_proyectos)

    fig = go.Figure(
        data = [go.Scatter(name=proyecto, x=proyectos.flow.index, y=proyectos.flow[proyecto].cumsum(), stackgroup='one') for proyecto in proyectos.proyectos]        
    )
    
    fig.update_layout(title='<b>Evolución de Proyectos</b>')
    fig.update_yaxes(title_text=moneda.upper())
    st.plotly_chart(fig, use_container_width=True)

    tmp = data_proyectos[::-1].fillna('').copy()
    nombre = 'gasto (' + moneda + ')'
    tmp[nombre] = tmp[moneda]
    tmp = tmp[['id','fecha',nombre,'categoria','sub_categoria_1','sub_categoria_2','proyecto','sub_proyecto','sistema','cuenta','proveedor','detalle',
                'comprobante','site']]
    tmp[nombre] = tmp[nombre].map('${:,.2f}'.format)

    st.subheader('Datos Seleccionados')

    gb = GridOptionsBuilder.from_dataframe(tmp)
    gb.configure_pagination()
    gb.configure_side_bar()
    gb.configure_default_column(groupable=True, value=True, enableRowGroup=True, aggFunc='sum', editable=True)
    gridOptions = gb.build()
    
    #gridOptions['columnDefs'] = [{'field':col, 'pivot':True, 'value':True} if col in ['categoria','sub_categoria_1'] else \
    #    {'field':col, 'pivot':False, 'value':True} for col in mayor.columns]
    AgGrid(tmp, gridOptions = gridOptions)#, enable_enterprise_modules=True)

    st.subheader('Treemaps')

    with st.form(key = 'Form'):
        campos1 = st.multiselect(
            'Campos Gráfico 1 (el orden importa)',
            ['Categoria','Proyecto','Sub_proyecto','Sistema','Destino'],
            ['Proyecto','Sub_proyecto','Categoria'])
        
        campos1 = list(map(str.lower, campos1))

        campos2 = st.multiselect(
            'Campos Gráfico 2 (el orden importa)', options=['Categoria','Proyecto','Sub_proyecto','Sistema','Destino'],
            default=['Categoria','Proyecto','Sub_proyecto'])
        
        campos2 = list(map(str.lower, campos2))

        submitted = st.form_submit_button(label = 'Submit')
    
    if submitted:
        data_proyectos[moneda] = data_proyectos[moneda].round(decimals=2)
        
        fig = px.treemap(data_proyectos, path=[px.Constant("Todos")] + campos1, values=moneda)
        fig.update_traces(root_color="lightgrey")
        fig.update_layout(margin = dict(t=50, l=25, r=25, b=25))
        st.subheader( ' --> '.join(map(str.title, campos1)) )
        st.plotly_chart(fig, use_container_width=True)

        fig = px.treemap(data_proyectos, path=[px.Constant("Todos")] + campos2, values=moneda)
        fig.update_traces(root_color="lightgrey")
        fig.update_layout(margin = dict(t=50, l=25, r=25, b=25))
        st.subheader( ' --> '.join(map(str.title, campos2)) )
        st.plotly_chart(fig, use_container_width=True)

        
        pivot = pivot_ui(
            data_proyectos[[
                'categoria',
                'sub_categoria_1',
                'proyecto',
                'sub_proyecto',
                'sistema',
                'destino',
                'cuenta',
                'detalle',
                'usd'
            ]],
            rows=['proyecto','sub_proyecto'],
            cols=['categoria'],
            vals=['usd'],
            aggregatorName='Sum',
            outfile_path='/tmp/pivottablejs.html'
            )
        st.subheader('Tabla Resumen')
        with open(pivot.src) as pivot:
            components.html(pivot.read(), width=900, height=1000, scrolling=True)