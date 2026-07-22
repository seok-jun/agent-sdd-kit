package example.order;

public class OrderCancelController {
    private final OrderCancelService service;

    public OrderCancelController(OrderCancelService service) {
        this.service = service;
    }

    public void cancel(long orderId) {
        service.cancel(orderId);
    }
}
