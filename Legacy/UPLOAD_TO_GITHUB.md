# Cómo publicar este repositorio en GitHub

Nombre recomendado:

```text
spmkit-data-hunter
```

Descripción recomendada:

```text
Discover and curate public AFM/SPM datasets for reproducible scientific software validation.
```

Temas recomendados:

```text
afm
spm
kpfm
force-spectroscopy
scientific-python
open-data
research-software
dataset-discovery
```

## Opción A: desde la Terminal

### 1. Descomprime el ZIP y entra a la carpeta

```bash
cd ~/Downloads/spmkit-data-hunter
```

Ajusta la ruta según dónde hayas descomprimido el archivo.

### 2. Comprueba que funciona

```bash
python3 src/spmkit_data_hunter.py --self-test
```

### 3. Crea el repositorio vacío en GitHub

En GitHub:

1. Pulsa `+`.
2. Selecciona `New repository`.
3. Escribe `spmkit-data-hunter`.
4. Elige `Public`.
5. No agregues README, `.gitignore` ni licencia, porque ya vienen incluidos.
6. Pulsa `Create repository`.

### 4. Inicializa Git y sube todo

```bash
git init
git add .
git commit -m "Initial release of SPM-Kit Data Hunter v2.0.0"
git branch -M main
git remote add origin https://github.com/kegouro/spmkit-data-hunter.git
git push -u origin main
```

GitHub puede pedirte iniciar sesión en el navegador o autenticarte con un token.

## Opción B: con GitHub Desktop

1. Descomprime el ZIP.
2. Abre GitHub Desktop.
3. Selecciona `File` → `Add Local Repository`.
4. Escoge la carpeta `spmkit-data-hunter`.
5. Si Git todavía no está inicializado, créalo desde la aplicación.
6. Haz el commit inicial.
7. Pulsa `Publish repository`.
8. Usa el nombre `spmkit-data-hunter` y déjalo público.

## Después de subirlo

1. Revisa que la acción `CI` aparezca en verde.
2. En `About`, agrega la descripción y los topics sugeridos.
3. Activa `Issues`.
4. Crea una release llamada `v2.0.0`.
5. Adjunta el ZIP solo como comodidad. El código principal debe vivir en los commits.
6. No subas carpetas `spm_benchmarks/`, `datasets/` ni archivos descargados.

## Release recomendada

Tag:

```text
v2.0.0
```

Título:

```text
SPM-Kit Data Hunter v2.0.0
```

Texto:

```text
First public release of SPM-Kit Data Hunter.

This release transforms the original dataset downloader into a validation-oriented benchmark curator. It discovers public AFM/SPM records through official Zenodo and Figshare APIs, classifies evidence, ranks candidates as Gold/Silver/Bronze, exports reproducible catalogs, and supports resumable checksum-verified downloads.
```
