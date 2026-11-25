# Llenado ZM_CAJA – CD Coquimbo

App Streamlit que calcula los movimientos para llenar al 100 % las ubicaciones de zona de movimiento **ZM_CAJ**
desde **ALMAC / ALMPIC**, respetando FEFO y priorizando restos de pallet.

## Archivos que se suben
- `OPERACIONES_DE_VIDA_UTIL.csv` (único archivo; ubicación, LPN, cantidad, estado y caducidad)

## Maestros incluidos (carpeta `maestros/`, del archivo maestro del gemelo digital)
- `ubicaciones.csv` – capacidad máxima por ubicación
- `preferencia.csv` – artículo asignado por ubicación (el orden del archivo se usa como secuencia)
- `zonas.csv` – zona de trabajo / movimiento

## Ejecutar
```
pip install -r requirements.txt
streamlit run app.py
```
