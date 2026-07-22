package example.order;

import java.util.List;

public class OrderCancelController {
    private final OrderCancelService service;

    public OrderCancelController(OrderCancelService service) {
        this.service = service;
    }

    public void cancel(long orderId, List<Long> itemIds) {
        service.cancel(orderId, itemIds);
    }
}
