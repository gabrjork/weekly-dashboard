# Guia: Fonte Plus Jakarta Sans no Streamlit Cloud

## 📋 Visão Geral

Este guia explica como a fonte **Plus Jakarta Sans** é instalada automaticamente para exportação PNG no Streamlit Cloud.

## 🔧 Arquivos Necessários

### 1. `packages.txt`
```
fonts-liberation
fonts-dejavu-core
fontconfig
```
**O que faz:** Instala pacotes de sistema necessários para gerenciamento de fontes no Ubuntu (base do Streamlit Cloud).

### 2. `weekly.py` (código de instalação automática)
O código no início do `weekly.py` faz:
- Detecta o sistema operacional
- Cria diretório de fontes se não existir
- Baixa Plus Jakarta Sans do Google Fonts
- Instala na pasta de fontes do usuário
- Atualiza cache de fontes (Linux)

## 🚀 Deploy no Streamlit Cloud

### Passo 1: Adicionar Arquivos ao Repositório
```bash
git add packages.txt weekly.py requirements.txt
git commit -m "Adicionar suporte a Plus Jakarta Sans para PNGs"
git push origin main
```

### Passo 2: Deploy Automático
O Streamlit Cloud irá:
1. Instalar pacotes do sistema (`packages.txt`)
2. Instalar dependências Python (`requirements.txt`)
3. Executar o app
4. Na primeira execução, a fonte será baixada e instalada automaticamente

## ✅ Verificação

### Como Saber se Está Funcionando:
1. Acesse o app no Streamlit Cloud
2. Vá para "Análise por Categoria"
3. Clique em "📥 PNG" em qualquer gráfico
4. Abra o PNG baixado
5. A fonte deve ser **Plus Jakarta Sans** (visível nos rótulos e números)

### Se Não Funcionar:
**Fallback Automático:** O app usa Arial/Helvetica se a instalação da fonte falhar.

**Debug:**
1. No Streamlit Cloud, clique em "Manage app"
2. Vá em "Logs"
3. Procure por mensagens como:
   - `"Aviso: Não foi possível instalar Plus Jakarta Sans"`
   - Erros de permissão ou rede

## 🔍 Alternativa: Fontes do Sistema

Se preferir usar fontes já disponíveis no sistema:

### Fontes Confiáveis no Streamlit Cloud (Ubuntu):
- **Liberation Sans** (similar à Arial)
- **DejaVu Sans** (similar à Verdana)
- **Ubuntu** (fonte padrão do Ubuntu)

### Alteração no Código:
Em `weekly.py`, substitua:
```python
family='Plus Jakarta Sans, -apple-system, BlinkMacSystemFont, sans-serif'
```

Por:
```python
family='Liberation Sans, DejaVu Sans, Arial, sans-serif'
```

## 📚 Recursos

- [Google Fonts - Plus Jakarta Sans](https://fonts.google.com/specimen/Plus+Jakarta+Sans)
- [Streamlit Deploy Docs](https://docs.streamlit.io/streamlit-community-cloud/deploy-your-app)
- [Kaleido - PNG Export](https://github.com/plotly/Kaleido)

## ⚠️ Notas Importantes

1. **Primeira Execução:** A fonte é baixada apenas uma vez (armazenada em session_state)
2. **Timeout:** O download tem timeout de 10 segundos
3. **Permissões:** O código funciona sem permissões de root/admin (instala na pasta do usuário)
4. **Cache:** No Linux, `fc-cache -f` atualiza o cache de fontes para que o Kaleido encontre a fonte

## 🐛 Troubleshooting

### Problema: Font não aparece nos PNGs
**Solução 1:** Reinicie o app no Streamlit Cloud (pode ser necessário limpar cache)
**Solução 2:** Verifique se `packages.txt` está no repositório root
**Solução 3:** Use fonte alternativa (Liberation Sans)

### Problema: Erro de permissão
**Solução:** O código já instala na pasta do usuário (não precisa de admin)

### Problema: Erro de rede
**Solução:** Verifique logs no Streamlit Cloud. Se persistir, mude para fonte do sistema.
