# Runbook — embeddings E5

O serviço `mentor-concursos-embeddings` usa somente `mentor-concursos-core`,
não publica portas e executa offline. O healthcheck só passa depois que o
artefato ONNX INT8 CPU, tokenizer, manifesto SHA-256, revisão e dimensão 384
são validados.

Para diagnosticar:

```bash
docker compose ps mentor-concursos-embeddings
docker logs --tail 100 mentor-concursos-embeddings
```

Ausência, checksum divergente ou backend diferente causa falha fechada. Não
montar cache do host nem baixar o modelo durante startup. O lock real fixa
ONNX Runtime CPU, tokenizers e dependências transitivas com hashes; atualização exige
novo snapshot, manifesto, build, teste sem rede, benchmark e rollback para a
tag anterior. Os pesos não entram no Git.

O runtime final não deve conter CUDA, PyTorch, compiladores ou caches. A
limpeza seletiva só pode remover imagens antigas de embeddings sem containers
dependentes, após conferência explícita de IDs; nunca usar prune global nem
remover volumes. A imagem atual aprovada é 0.3.0, fixada por digest no Compose.
