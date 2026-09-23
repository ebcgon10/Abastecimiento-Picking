# Llenado ZM_CAJA – CD Coquimbo

App Streamlit que calcula los movimientos para llenar al 100 % las ubicaciones de zona de movimiento **ZM_CAJ**
desde **ALMAC / ALMPIC**, respetando FEFO y priorizando restos de pallet.

## Archivos que se suben
- `CUADRATURA_DE_STOCK.csv`
- `OPERACIONES_DE_VIDA_UTIL.csv`

## Maestros incluidos (carpeta `maestros/`)
- `ubicaciones.csv` – capacidad máxima por ubicación
- `preferencia.csv` – artículo asignado y secuencia de ruta
- `zonas.csv` – zona de trabajo / movimiento / recogida

## Ejecutar
```
pip install -r requirements.txt
streamlit run app.py
```
