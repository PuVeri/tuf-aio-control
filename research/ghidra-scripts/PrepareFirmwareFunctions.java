// Applies evidence-based static annotations to the Ghidra project.
// @category TufAio

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.SourceType;

public class PrepareFirmwareFunctions extends GhidraScript {
	private void renameFunction(String addressText, String name) throws Exception {
		Address address = toAddr(addressText);
		Function function = getFunctionContaining(address);
		if (function == null) {
			function = getFunctionAt(address);
		}
		if (function == null) {
			throw new IllegalStateException("no function at " + address);
		}
		function.setName(name, SourceType.USER_DEFINED);
	}

	@Override
	public void run() throws Exception {
		MemoryBlock block = currentProgram.getMemory().getBlock(toAddr("00100000"));
		if (block == null) {
			throw new IllegalStateException("firmware memory block missing");
		}
		block.setWrite(false);

		Address dataReceiver = toAddr("001297e8");
		if (getFunctionAt(dataReceiver) == null) {
			disassemble(dataReceiver);
			Function function = createFunction(dataReceiver, null);
			if (function == null) {
				throw new IllegalStateException("could not create data receiver function");
			}
		}

		renameFunction("00126dfc", "device_command_dispatch_candidate");
		renameFunction("001293f8", "transport_dispatch_candidate");
		renameFunction("001296d8", "segmented_command_receive_candidate");
		renameFunction("001297e8", "segmented_data_receive_candidate");
		renameFunction("001298f8", "response_packet_builder_candidate");
		renameFunction("00129d84", "protocol_task_setup_candidate");
		renameFunction("0012c12c", "usb_setup_request_dispatch");
		renameFunction("0012ced0", "usb_event_dispatch_candidate");
	}
}
