# Plano de implementação: Confirmation Flow

**Pré-requisitos:**
- F06 implementado: execução de turno, leitura de pendências, rota de mensagens e Runner da aplicação disponíveis
- F07 implementado: especialista `reservas` com a tool de reserva preparada para a resposta da confirmação
- F08 implementado: especialista `visitantes` com a tool de autorização preparada para a resposta da confirmação
- PostgreSQL do compose no ar e saudável, com as databases `aurora` e `aurora_test`
- `google-adk==2.2.0` já instalado; nenhuma dependência nova e nenhuma variável de ambiente nova

### Fase 1: Regra de pendência

**1. Regra nova de pendência** - Mudar a leitura das pendências para que um pedido de confirmação só deixe a lista quando a tool em espera tiver um resultado gravado depois da resposta do morador. A especificação define pedido, resposta, resultado e os três estados de um pedido.

**2. Autor do pedido no item pendente** - Fazer o item pendente carregar o agente que pediu a confirmação, sem levar esse dado para a resposta HTTP.

**3. Resultado da tool em espera** - Oferecer a leitura do resultado que a tool em espera gravou depois da resposta a um pedido, para a rota decidir o desfecho pelo que está na sessão.

### Fase 2: Retomada pelo especialista

**4. Runners de retomada** - Criar a fábrica que monta um Runner por especialista que pede confirmação, cada um com um especialista próprio construído pelas fábricas que já existem, sobre o mesmo serviço de sessão e o mesmo nome de aplicação do ADK.

**5. Runners de retomada no ciclo de vida** - Criar os Runners de retomada na subida da aplicação, deixá-los acessíveis às rotas e fechá-los na parada.

**6. Execução de turno reutilizável** - Separar, no serviço de conversa, a execução do Runner da montagem da resposta, para que a rota de confirmações saiba se o turno produziu texto. O comportamento da rota de mensagens não muda.

### Fase 3: Rota de confirmações

**7. Resposta a uma confirmação** - Criar o serviço que confere se o id está pendente na sessão, monta a mensagem de resposta no formato do ADK, escolhe o Runner de retomada pelo autor do pedido e executa o turno. Os passos estão na especificação.

**8. Desfecho pelo que ficou gravado** - Depois do turno, reler a sessão e decidir a resposta: confirmação resolvida ou retomada que falhou. Na falha, o item continua pendente e o texto diz que a ação não foi executada.

**9. Texto da resposta** - Usar o texto do especialista e, quando ele não existir, o texto tirado do resultado da tool ou a frase fixa de aprovação ou de recusa. A falha do modelo nesta rota não vira erro HTTP.

**10. Rota e corpo** - Expor a rota de confirmações com o corpo validado, a resposta no formato da rota de mensagens e o `409` para todo id que não está pendente na sessão.

### Fase 4: Insumos de verificação

**11. Modelo roteirizado com repasse** - Permitir que uma entrada do roteiro seja calculada a partir da requisição ao modelo e entregar a entrada que repassa a mensagem do último resultado de tool.

**12. Tool de teste que falha sob comando** - Fazer a tool de teste com confirmação poder falhar na próxima execução, com um erro que não é do banco, antes de registrar a execução.

**13. Runners de retomada roteirizados** - Produzir a aplicação em processo com os Runners de retomada recebendo o modelo roteirizado dos especialistas, com a opção da tool de teste e da engine sem banco, pelo mecanismo de preparação do projeto.

**14. Estados de sessão** - Ajustar a sessão "com confirmação respondida" do F06 para incluir o resultado da tool e produzir a sessão com resposta sem resultado que o contrato declara.
