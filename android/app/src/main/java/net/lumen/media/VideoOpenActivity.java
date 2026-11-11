package net.lumen.media;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.os.Bundle;
import android.net.Uri;
import android.view.ContextThemeWrapper;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.drawable.InsetDrawable;
import android.graphics.drawable.RippleDrawable;
import android.widget.Button;
import android.widget.TextView;
import androidx.core.graphics.ColorUtils;
import androidx.appcompat.app.AlertDialog;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;
import com.google.android.material.shape.MaterialShapeDrawable;
import com.google.android.material.shape.ShapeAppearanceModel;
import net.lumen.media.ui.theme.NativeActionTokens;
import java.io.IOException;

/** The only exported video entry: forwards one validated read-only URI, never library extras. */
public final class VideoOpenActivity extends Activity {
    static Intent forward(Activity context,Intent incoming)throws IOException{
        Uri uri=ExternalVideoSource.routingUri(incoming);
        Intent target=new Intent(context,PlayerActivity.class).setAction(Intent.ACTION_VIEW).setDataAndType(uri,incoming.getType())
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        target.setClipData(ClipData.newRawUri(context.getString(R.string.external_video_title),uri));return target;
    }
    @Override protected void onCreate(Bundle state){
        super.onCreate(state);
        try{startActivity(forward(this,getIntent()));finish();}
        catch(IOException error){showError(error.getMessage());}
    }
    private void showError(String message){
        ContextThemeWrapper themed=new ContextThemeWrapper(this,R.style.LumenNativeActionsDark);
        MaterialShapeDrawable surface=new MaterialShapeDrawable(ShapeAppearanceModel.builder().setAllCornerSizes(MediaStyle.dp(this,NativeActionTokens.cardCornerDp())).build());surface.setFillColor(ColorStateList.valueOf(NativeActionTokens.surfaceContainerHigh(true)));
        AlertDialog dialog=new MaterialAlertDialogBuilder(themed,com.google.android.material.R.style.ThemeOverlay_Material3_MaterialAlertDialog).setBackground(surface).setTitle(R.string.external_video_error_title).setMessage(message).setPositiveButton(R.string.external_video_close,(view,which)->finish()).setOnCancelListener(view->finish()).show();
        TextView title=dialog.findViewById(androidx.appcompat.R.id.alertTitle),body=dialog.findViewById(android.R.id.message);if(title!=null){title.setTextColor(NativeActionTokens.onSurface(true));title.setTextSize(NativeActionTokens.titleSp());}if(body!=null){body.setTextColor(NativeActionTokens.onSurfaceVariant(true));body.setTextSize(NativeActionTokens.bodySp());}
        Button close=dialog.getButton(AlertDialog.BUTTON_POSITIVE);int primary=NativeActionTokens.primary(true),inset=MediaStyle.dp(this,NativeActionTokens.insetDp());MaterialShapeDrawable clear=new MaterialShapeDrawable(ShapeAppearanceModel.builder().setAllCornerSizes(MediaStyle.dp(this,NativeActionTokens.cornerDp())).build());clear.setFillColor(ColorStateList.valueOf(Color.TRANSPARENT));close.setBackgroundTintList(null);close.setBackground(new InsetDrawable(new RippleDrawable(ColorStateList.valueOf(ColorUtils.setAlphaComponent(primary,31)),clear,null),0,inset,0,inset));close.setTextColor(primary);close.setAllCaps(false);close.setIncludeFontPadding(false);close.setTextSize(NativeActionTokens.labelSp());close.setMinHeight(MediaStyle.dp(this,NativeActionTokens.touchDp()));close.setMinimumHeight(MediaStyle.dp(this,NativeActionTokens.touchDp()));close.setMinWidth(MediaStyle.dp(this,NativeActionTokens.touchDp()));close.setMinimumWidth(MediaStyle.dp(this,NativeActionTokens.touchDp()));close.setPadding(MediaStyle.dp(this,NativeActionTokens.horizontalPaddingDp()),inset+MediaStyle.dp(this,NativeActionTokens.verticalPaddingDp()),MediaStyle.dp(this,NativeActionTokens.horizontalPaddingDp()),inset+MediaStyle.dp(this,NativeActionTokens.verticalPaddingDp()));
    }
}
