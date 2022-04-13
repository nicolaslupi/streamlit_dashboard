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

colores = ['#1f77b4', '#ff7f0e', '#2ca02c','#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
Caja = set(['caja ars','caja usd','ml','banco','electronica','estructuras','propulsion','accounting','sendwyre'])
Transferencias = set(['epic'])
Aportes = set(['aportes','montero'])
Deudas = set(['cuentas a pagar'])
Mission_costs = set(['rideshare costs'])
OPEX = set(['transporte','consumibles generales','consumibles de oficina','consumibles de ensayos',
            'consumibles para produccion de propelente',])
Otros_gastos = set(['impuestos','legal','variacion de inventario','otros gastos varios','perdida por tc','perdida por arqueo'])
Otros_ingresos = set(['ganancia por tc','ganancia por arqueo','otros ingresos varios'])
FOPEX = set(['sg&a salaries','tech salaries','suscripciones','alquiler'])
CAPEX = set(['herramientas','materiales','infraestructura','utilaje','mano de obra','rodados','equipo de oficina'])
general_rd = set(['propulsion r&d','electronics r&d'])
Hardware = set(['test equipment','vehicle r&d', 'vehicle development', 'flight tugs', 'propellant production hardware']).union(general_rd)

cuentas_gastos = OPEX.union(Mission_costs, Otros_gastos, FOPEX, CAPEX, Hardware)
activo = Caja.union(Mission_costs, OPEX, Otros_gastos, FOPEX, CAPEX, Hardware, Transferencias)
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

class Proyecto():
  def __init__(self, data, months):
    
    self.sub_proyectos = set(data.sub_proyecto_1)
    self.flow = pd.DataFrame(index=months)
    flow_aux = pd.DataFrame(index=pd.unique(data.month))
    sumas = pd.pivot_table( data, values='usd', index='month', columns=['sub_proyecto_1','destino'], aggfunc=sum, fill_value=0 )
    restas = pd.pivot_table( data, values='usd', index='month', columns=['sub_proyecto_1','origen'], aggfunc=sum, fill_value=0 )
    restas.columns.names = ['sub_proyecto_1','destino']
    tmp = sumas.sub(restas, axis=1, fill_value=0)
    flow_aux[list(self.sub_proyectos)]  = np.array([tmp[sub_proyecto][set(tmp[sub_proyecto].columns)&cuentas_gastos].sum(axis=1) for sub_proyecto in self.sub_proyectos]).transpose()
    self.flow = self.flow.join(flow_aux).fillna(0)
    self.stock = self.flow.cumsum()

class Proyectos():
  def __init__(self, data):
    self.flow = pd.DataFrame(index=pd.unique(data.month))
    self.names = set(data.proyecto)
    sumas = pd.pivot_table( data, values='usd', index='month', columns=['proyecto','destino'], aggfunc=sum, fill_value=0)
    restas = pd.pivot_table( data, values='usd', index='month', columns=['proyecto','origen'], aggfunc=sum, fill_value=0)
    restas.columns.names = ['proyecto','destino']
    tmp = sumas.sub(restas, axis=1, fill_value=0)
    
    self.flow[list(self.names)] = np.array([tmp[proyecto][set(tmp[proyecto].columns)&cuentas_gastos].sum(axis=1) for proyecto in self.names]).transpose()
    self.flow['Outflows'] = self.flow.sum(axis=1)
    self.stock = self.flow.cumsum()
    self.flow['MA'] = self.flow['Outflows'].rolling(window=3).mean()
    #self.flow.iloc[-1,-1] = self.flow.iloc[-2,-1]

    self.proyectos = {proyecto: Proyecto(data[data.proyecto==proyecto], pd.unique(data.month)) for proyecto in self.names } 

@st.cache(allow_output_mutation=True)
def load_data(url, filename):
    if os.path.exists(filename):
        os.remove(filename)
    wget.download(url, filename)

    data = pd.read_excel(filename, sheet_name='Input', header=2)
    data['site'] = 'Epic'
    data_us = pd.read_excel(filename, sheet_name='Input US', header=2)
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

@st.cache(allow_output_mutation=True)
def load_teams(url, filename):
    if os.path.exists(filename):
        os.remove(filename)
    wget.download(url, filename)

    labor = pd.read_excel(filename, sheet_name='Roles', header=0, index_col=0)
    labor = labor.transpose()
    labor.drop(labels=np.nan, axis=1, inplace=True)

    teams = pd.read_excel(filename, sheet_name='Teams', header=0, index_col=0)
    teams = teams.transpose()
    teams.drop(labels=np.nan, axis=1, inplace=True)

    # L = pd.DataFrame(labor.sum(axis=1), columns=['L'])
    # tech = pd.DataFrame(
    #     labor[labor.columns[~labor.columns.isin(['Management', 'Accounting', 'Media & Sales'])]].sum(axis=1),
    #     columns=['tech']
    # )
    # sga = pd.DataFrame(
    #     labor[labor.columns[labor.columns.isin(['Management', 'Accounting', 'Media & Sales'])]].sum(axis=1),
    #     columns=['sga']
    # )

    # prop_labor = pd.DataFrame(
    #     labor[['Mech Eng', 'Mech Tech', 'Other Eng', 'Other Tech']].sum(axis=1),
    #     columns=['prop']
    # )

    # elec_labor = pd.DataFrame(
    #     labor[['Elec Eng', 'Elec Tech']].sum(axis=1),
    #     columns=['elec']
    # )

    return teams

@st.cache(allow_output_mutation=True)
def filter(data, sites, moneda):
    data = data[data.site.isin(sites)].reset_index(drop=True)
    flow = pd.pivot_table( data, values=moneda, index='month', columns='destino', aggfunc=sum, fill_value=0).sub( \
           pd.pivot_table( data, values=moneda, index='month', columns='origen', aggfunc=sum, fill_value=0), \
           axis=1, fill_value=0)

    flow['Caja'] = flow[set(flow.columns)&Caja].sum(axis=1)
    flow['Mission_costs'] = flow[set(flow.columns)&Mission_costs].sum(axis=1)
    flow['FOPEX'] = flow[set(flow.columns)&FOPEX].sum(axis=1)
    flow['OPEX'] = flow[set(flow.columns)&OPEX].sum(axis=1)
    flow['CAPEX'] = flow[set(flow.columns)&CAPEX].sum(axis=1)
    flow['Hardware'] = flow[set(flow.columns)&Hardware].sum(axis=1)
    flow['Otros_gastos'] = flow[set(flow.columns)&Otros_gastos].sum(axis=1)

    flow['Outflows'] = flow[['Mission_costs','FOPEX','OPEX','CAPEX','Hardware','Otros_gastos']].sum(axis=1)
    
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

    ## Estado de Caja
    
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

    ## Burn & Runway
    
    st.subheader('Burn & Runway')
    cost_names = ['Todos','Mission_costs','FOPEX','OPEX','CAPEX','Hardware','Otros_gastos']
    cuentas_elegidas = st.multiselect('Cuentas para Burn', cost_names, ['Todos'])
    
    aux_flow = flow.copy()
    
    if 'Todos' in cuentas_elegidas:
        cuentas_elegidas = cost_names
    else:
        aux_flow.Outflows = aux_flow[cuentas_elegidas].sum(axis=1)
        aux_flow.MA = aux_flow.Outflows.rolling(window=3).mean()
        aux_flow.iloc[-1,-1] = aux_flow.iloc[-2,-1]

    st.write('Burn actual:', moneda.upper(), '{:,.0f} por mes'.format(aux_flow.tail(1)['MA'].values[0]))
    st.write('Runway: {:,.0f} meses'.format((stock.tail(1)['Caja'] / aux_flow.tail(1)['MA']).values[0]))

    fig = make_subplots( specs = [[{'secondary_y':True}]] )

    fig.add_trace(
        go.Scatter(
            x=aux_flow.index,
            y=aux_flow.MA,
            name='Burn'
        ),
        secondary_y=False
    )

    fig.add_trace(
        go.Scatter(
            x=aux_flow.index,
            y=stock.Caja / aux_flow.MA,
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

def gastos(data, flow, moneda, date_range):
    data = data[data.destino.isin(cuentas_gastos)].reset_index(drop=True).copy()
    
    fig = go.Figure(data=[
                        go.Bar(
                            name=cuenta,
                            x=flow.index,
                            y=flow[cuenta],
                            hoverinfo='text',
                            text=['{}<br>Total: ${:,.0f} <br>{}: ${:,.0f}'.format(date.strftime('%b-%Y'), total, cuenta, cat) for date, total, cat in zip(flow.index, flow.Outflows, flow[cuenta])])
                            for cuenta in ['Mission_costs','FOPEX','OPEX','Hardware','CAPEX','Otros_gastos']
                    ])
    
    fig.add_trace(
        go.Scatter(
            x=flow.index,
            y=flow.MA,
            hoverinfo='text',
            line_color='darkorange',
            text=['{}<br>MA: ${:,.0f}'.format(date.strftime('%b-%Y'), ma) for date, ma in zip(flow.index, flow.MA)],
            name='MA'
        )
    )

    fig.update_layout(barmode='stack', title='<b>Gastos Mensuales por Categoría</b>')#, height=500)
    fig.update_yaxes(title_text=moneda.upper())
    st.plotly_chart(fig, use_container_width=True)

    proyectos = get_proyectos(data)
    fig = go.Figure(data=[
                      go.Bar(
                          name=col,
                          x=proyectos.flow.index,
                          y=proyectos.flow[col],
                          hoverinfo='text',
                          text=['{}<br>Total: ${:,.0f} <br>{}: ${:,.0f}'.format(date.strftime('%b-%Y'), total, col, cat) for date, total, cat in zip(proyectos.flow.index, proyectos.flow.Outflows, proyectos.flow[col])]) for col in proyectos.names
                     ])
    fig.add_trace(
        go.Scatter(
            x=proyectos.flow.index,
            y=proyectos.flow.MA,
            hoverinfo='text',
            line_color='darkorange',
            text=['{}<br>MA: ${:,.0f}'.format(date.strftime('%b-%Y'), ma) for date, ma in zip(proyectos.flow.index, proyectos.flow.MA)],
            name='MA'
        )
    )

    fig.update_layout(barmode='stack')
    fig.update_layout(title='<b>Gastos Mensuales por Destino</b>')
    fig.update_yaxes(title_text=moneda.upper())
    st.plotly_chart(fig, use_container_width=True)

    pivot = pivot_ui(
        data.loc[
            data.fecha.between(date_range[0], date_range[1]),
            ['categoria',
            'sub_categoria_1',
            'proyecto',
            'sub_proyecto_1',
            'sub_proyecto_2',
            'sub_proyecto_3',
            'sistema',
            'destino',
            'cuenta',
            'proveedor',
            'detalle',
            'usd'
        ]],
        rows=['proyecto','sub_proyecto_1','categoria'],
        #cols=['categoria'],
        vals=['usd'],
        aggregatorName='Sum',
        outfile_path='/tmp/pivottablejs.html'
        )
    st.title('Tabla Resumen')
    st.write('Para el período ' + str(date_range[0]) + ' - ' + str(date_range[1]))
    with open(pivot.src) as pivot:
        components.html(pivot.read(), width=900, height=1000, scrolling=True)

    st.title('Proyectos')
    st.write('Para el período ' + str(date_range[0]) + ' - ' + str(date_range[1]))
        
    

    #data['month'] = data.month.apply(lambda fecha: dt.datetime.date(pd.to_datetime(fecha)))
    data_proyectos = data[
                            (data.fecha.between(date_range[0], date_range[1]))
                            #(data.proyecto.isin(proyectos_elegidos))
                        ].sort_values(['fecha','id']).reset_index(drop=True).copy()

    proyectos = get_proyectos(data_proyectos)

    # subproyectos = st.checkbox(label='Visualizar Sub Proyectos')
    # if subproyectos:
    #     fig = go.Figure()
    #     i=0

    #     for proyecto in proyectos.names:
    #         for sub_proyecto in proyectos.proyectos[proyecto].sub_proyectos:
    #             fig.add_trace(
    #             go.Scatter(
    #                 x=proyectos.proyectos[proyecto].stock.index,
    #                 y=proyectos.proyectos[proyecto].stock[sub_proyecto],
    #                 name=sub_proyecto + ' ' + proyecto,
    #                 stackgroup='one',
    #                 line_color=colores[ i % len(colores) ]
    #             )
    #         )
    #         i+=1
    # else:
    #     fig = go.Figure(
    #         data = [go.Scatter(name=proyecto, x=proyectos.stock.index, y=proyectos.stock[proyecto], stackgroup='one') for proyecto in proyectos.names]        
    #     )
    
    fig = go.Figure(data=[
                      go.Bar(
                          name=col,
                          x=proyectos.flow.index,
                          y=proyectos.flow[col],
                          hoverinfo='text',
                          text=['{}<br>Total: ${:,.0f} <br>{}: ${:,.0f}'.format(date.strftime('%b-%Y'), total, col, cat) for date, total, cat in zip(proyectos.flow.index, proyectos.flow.Outflows, proyectos.flow[col])]) 
                          for col in proyectos.names
                     ])


    fig.update_layout(barmode='stack')
    
    fig.update_layout(title='<b>Evolución de Proyectos</b>')
    fig.update_yaxes(title_text=moneda.upper())
    st.plotly_chart(fig, use_container_width=True)

    
    st.subheader('Treemaps')

    with st.form(key = 'Form'):
        #with st.expander('Proyectos'):
        proyectos = ['Todos'] + list(set(data.proyecto))
        
        proyectos_elegidos = st.multiselect('Proyectos Elegidos', proyectos, ['Todos'])
        if 'Todos' in proyectos_elegidos:
            proyectos_elegidos = proyectos
        
        campos1 = st.multiselect(
            'Campos Gráfico 1 (el orden importa)',
            ['Categoria','Sub_categoria_1','Proyecto','Sub_proyecto_1','Sub_proyecto_2','Sub_proyecto_3','Sistema','Destino','Cuenta','Proveedor'],
            ['Proyecto','Sub_proyecto_1','Categoria', 'Sub_categoria_1', 'Cuenta'])
        
        campos1 = list(map(str.lower, campos1))

        campos2 = st.multiselect(
            'Campos Gráfico 2 (el orden importa)',
            options=['Categoria','Sub_categoria_1','Proyecto','Sub_proyecto_1','Sub_proyecto_2','Sub_proyecto_3','Sistema','Destino','Cuenta','Proveedor'],
            default=['Categoria','Sub_categoria_1','Proyecto','Sub_proyecto_1','Cuenta'])
        
        campos2 = list(map(str.lower, campos2))

        submitted = st.form_submit_button(label = 'Submit')
    
    if submitted:
        data_proyectos = data_proyectos[
                            (data_proyectos.proyecto.isin(proyectos_elegidos))
                        ].sort_values(['fecha','id']).reset_index(drop=True).copy()

        data_proyectos[moneda] = data_proyectos[moneda].round(decimals=2)
        
        fig = px.treemap(data_proyectos, path=[px.Constant("Todos")] + campos1, values=moneda)
        fig.update_traces(root_color="lightgrey")
        fig.update_layout(margin = dict(t=50, l=25, r=25, b=25))
        fig.data[0].textinfo = 'label+text+value'
        st.subheader( ' --> '.join(map(str.title, campos1)) )
        st.plotly_chart(fig, use_container_width=True)

        fig = px.treemap(data_proyectos, path=[px.Constant("Todos")] + campos2, values=moneda)
        fig.update_traces(root_color="lightgrey")
        fig.update_layout(margin = dict(t=50, l=25, r=25, b=25))
        fig.data[0].textinfo = 'label+text+value'
        st.subheader( ' --> '.join(map(str.title, campos2)) )
        st.plotly_chart(fig, use_container_width=True)

    st.subheader('Datos Seleccionados')

    tmp = data_proyectos[::-1].fillna('').copy()
    nombre = 'gasto (' + moneda + ')'
    tmp[nombre] = tmp[moneda]
    tmp = tmp[['id','fecha',nombre,'categoria','sub_categoria_1','sub_categoria_2','proyecto','sub_proyecto_1','sistema','cuenta','proveedor','detalle',
                'comprobante','site']]
    tmp[nombre] = tmp[nombre].map('${:,.2f}'.format)
    
    gb = GridOptionsBuilder.from_dataframe(tmp)
    gb.configure_pagination()
    gb.configure_side_bar()
    gb.configure_default_column(groupable=True, value=True, enableRowGroup=True, aggFunc='sum', editable=True)
    gridOptions = gb.build()
    
    #gridOptions['columnDefs'] = [{'field':col, 'pivot':True, 'value':True} if col in ['categoria','sub_categoria_1'] else \
    #    {'field':col, 'pivot':False, 'value':True} for col in mayor.columns]
    AgGrid(tmp, gridOptions = gridOptions)#, enable_enterprise_modules=True)

#%% APORTES

def aportes(data, moneda, date_range):
    aportes = data[data.sub_categoria_1 == 'Inyección de Capital'].reset_index(drop=True).copy()
    aportes.detalle = aportes.detalle.fillna('')
    aportes = aportes[aportes.cuenta != 'montero incorporated'].reset_index(drop=True)
    aportes['tranche'] = 'NA'
    aportes.loc[aportes.detalle.str.contains('22m'), 'tranche'] = '22M'
    aportes.loc[aportes.detalle.str.contains('30m'), 'tranche'] = '30M'
    aportes.loc[aportes.detalle.str.contains('40m'), 'tranche'] = '40M'

    st.write('Total Aportes: USD {:,.0f}'.format(aportes.usd.sum()))
    
    tabla_aportes = pd.pivot_table(data=aportes, values='usd', index='month', columns='site', aggfunc=sum, fill_value=0)
    
    fig = go.Figure(data=[
                      go.Bar(
                          name=col,
                          x=tabla_aportes.index,
                          y=tabla_aportes[col])
                          for col in tabla_aportes
                     ])


    fig.update_layout(barmode='stack')
    
    fig.update_layout(title='<b>Historial de Aportes</b>')
    fig.update_yaxes(title_text='USD')
    st.plotly_chart(fig, use_container_width=True)


    pivot = pivot_ui(
        aportes.loc[
            aportes.fecha.between(date_range[0], date_range[1]),
            [
                'fecha',
                'destino',
                'cuenta',
                'detalle',
                'tranche',
                'site',
                'usd',
            ]
        ],
        rows=['tranche'],
        cols=['site'],
        vals=['usd'],
        aggregatorName='Sum',
        outfile_path='/tmp/pivottablejs.html'
        )
    st.header('Resumen de Aportes')
    st.write('Para el período ' + str(date_range[0]) + ' - ' + str(date_range[1]))
    with open(pivot.src) as pivot:
        components.html(pivot.read(), width=900, height=1000, scrolling=True)


#%% EQUIPO

def equipo(data, teams, moneda, date_range):
    payroll = pd.concat([data[data.sub_categoria_1.str.contains('Sala')].groupby('month').usd.sum(),
                     teams.sum(axis=1)], axis=1)
    payroll.columns = ['Payroll', 'Team Size']
    fig = make_subplots( specs = [[{'secondary_y':True}]] )

    fig.add_trace(
        go.Bar(
            x=payroll.index,
            y=payroll.Payroll,
            name='Payroll (left)'
        ),
        secondary_y=False
    )

    fig.add_trace(
        go.Scatter(
            x=payroll.index,
            y=payroll['Team Size'],
            name='Team Size (right)'
        ),
        secondary_y=True
    )

    fig.update_yaxes(title_text="US$ per month", secondary_y=False)
    fig.update_yaxes(title_text="Team Size", secondary_y=True)
    fig.update_layout(title='<b>Payroll y Equipo</b>')
    st.plotly_chart(fig, use_container_width=True)