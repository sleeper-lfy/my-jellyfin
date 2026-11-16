package net.lumen.media;

import android.app.Activity;
import android.content.Context;
import android.view.ContextThemeWrapper;
import android.widget.LinearLayout;
import android.widget.TextView;
import com.google.android.material.bottomsheet.BottomSheetDialog;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.progressindicator.CircularProgressIndicator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.function.Consumer;
import net.lumen.media.ui.theme.NativeActionTokens;
import org.json.JSONArray;
import org.json.JSONObject;

/** An explicit playback action has its own lifetime, independent of page refreshes. */
final class ShuffleRequest implements AutoCloseable {
    interface Result {void accept(JSONObject result)throws Exception;}
    private final Activity activity;
    final ExecutorService worker=Executors.newFixedThreadPool(2);
    private int sequence;
    private Api.Cancellation cancellation;
    private Future<?> future;
    private BottomSheetDialog progress;
    private boolean closed;

    ShuffleRequest(Activity activity){this.activity=activity;}
    void start(Api client,String path,Result result,Consumer<Exception> failed){
        cancel();if(closed||activity.isDestroyed()||activity.isFinishing())return;
        final int ticket=sequence;final Api.Cancellation current=new Api.Cancellation();cancellation=current;
        showProgress();
        future=worker.submit(()->{
            try{
                JSONObject response=client.post("/api/queue/from-browse",new JSONObject().put("browse_path",path),current);
                JSONArray ids=response.getJSONArray("ids");for(int i=0;i<ids.length();i++)if(ids.getLong(i)<=0)throw new Exception(activity.getString(R.string.global_shuffle_invalid_response));
                activity.runOnUiThread(()->{
                    if(!active(ticket,current))return;finish();
                    try{result.accept(response);}catch(Exception error){failed.accept(error);}
                });
            }catch(Exception error){activity.runOnUiThread(()->{if(active(ticket,current)){finish();failed.accept(error);}});}
        });
    }
    private boolean active(int ticket,Api.Cancellation current){return !closed&&!activity.isDestroyed()&&!activity.isFinishing()&&ticket==sequence&&!current.cancelled();}
    private void showProgress(){
        Context context=new ContextThemeWrapper(activity,R.style.LumenNativeActionsDark);
        BottomSheetDialog dialog=new BottomSheetDialog(context,R.style.LumenLibraryFilterSheet){
            @Override public void cancel(){if(progress==this)ShuffleRequest.this.cancel();super.cancel();}
        };progress=dialog;
        LinearLayout content=new LinearLayout(dialog.getContext());content.setOrientation(LinearLayout.VERTICAL);content.setTag("shuffleProgress");
        int padding=MediaStyle.dp(context,NativeActionTokens.pageDp());content.setPadding(padding,padding,padding,padding);
        TextView title=new TextView(context);title.setText(R.string.shuffle_loading_title);title.setTextAppearance(com.google.android.material.R.style.TextAppearance_Material3_TitleMedium);content.addView(title);
        CircularProgressIndicator indicator=new CircularProgressIndicator(context);indicator.setIndeterminate(true);indicator.setContentDescription(activity.getString(R.string.shuffle_loading));
        LinearLayout.LayoutParams size=new LinearLayout.LayoutParams(MediaStyle.dp(context,48),MediaStyle.dp(context,48));size.topMargin=padding;size.bottomMargin=padding;content.addView(indicator,size);
        TextView message=new TextView(context);message.setText(R.string.shuffle_loading);message.setTextAppearance(com.google.android.material.R.style.TextAppearance_Material3_BodyMedium);content.addView(message);
        MaterialButton cancel=(MaterialButton)MediaStyle.action(context);cancel.setText(R.string.global_shuffle_cancel);cancel.setTag("shuffleCancel");BiliAuxiliaryUi.textAction(cancel,false);cancel.setOnClickListener(view->dialog.cancel());
        LinearLayout.LayoutParams action=new LinearLayout.LayoutParams(-1,-2);action.topMargin=padding;content.addView(cancel,action);
        dialog.setContentView(content);dialog.show();dialog.getBehavior().setState(com.google.android.material.bottomsheet.BottomSheetBehavior.STATE_EXPANDED);
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(content,(view,insets)->{int bottom=insets.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars()).bottom;view.setPadding(padding,padding,padding,padding+bottom);return insets;});
        androidx.core.view.ViewCompat.requestApplyInsets(content);
    }
    private void finish(){cancellation=null;future=null;BottomSheetDialog shown=progress;progress=null;if(shown!=null)shown.dismiss();}
    void cancel(){sequence++;if(cancellation!=null)cancellation.cancel();if(future!=null)future.cancel(true);finish();if(worker instanceof java.util.concurrent.ThreadPoolExecutor)((java.util.concurrent.ThreadPoolExecutor)worker).purge();}
    @Override public void close(){if(closed)return;cancel();closed=true;worker.shutdownNow();}
}
