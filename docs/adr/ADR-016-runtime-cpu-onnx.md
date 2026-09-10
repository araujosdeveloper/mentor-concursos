# ADR-016 — Runtime CPU enxuto para embeddings

O runtime de produção foi migrado de PyTorch/Transformers para ONNX Runtime
CPU com quantização dinâmica INT8. A conversão foi feita em ambiente
temporário a partir da revisão E5 aprovada, com mean-pooling mascarado e
normalização L2 preservados. O grafo operacional é `model.onnx`, opset 17,
dimensão 384, acompanhado de tokenizer JSON e manifesto SHA-256.

A comparação sintética mostrou cosine aproximado de 0,998 entre INT8 e o
baseline PyTorch nos pares avaliados, sem dependências CUDA na imagem final.
A imagem caiu de aproximadamente 11,1 GB virtuais/10,9 GB exclusivos para
756 MB virtuais/570 MB exclusivos, mantendo o limite de 768 MiB e consumo
observado de aproximadamente 452 MiB após aquecimento.

O snapshot PyTorch local foi removido somente depois de startup, restart,
inferência, benchmark e healthcheck aprovados. O rollback operacional usa a
imagem 0.3.0 fixada por digest e o checkpoint desta fase; nova versão de
modelo exige nova conversão, manifesto, benchmark e avaliação.
